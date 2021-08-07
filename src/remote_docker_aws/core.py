import os
import shlex
import subprocess
from getpass import getuser
from typing import Dict, List

from unison_gitignore.parser import GitIgnoreToUnisonIgnore

from .config import RemoteDockerConfigProfile
from .constants import (
    INSTANCE_USERNAME,
    PORT_MAP_TYPE,
)
from .providers import AWSInstanceProvider, InstanceProvider
from .util import get_replica_and_sync_paths_for_unison, logger


class RemoteDockerClient:
    def __init__(
        self,
        instance: InstanceProvider,
        local_port_forwards: PORT_MAP_TYPE,
        remote_port_forwards: PORT_MAP_TYPE,
        ssh_key_path: str,
        sync_dirs: List[str],
        sync_ignore_patterns: List[str],
    ):
        self.instance = instance
        self.local_port_forwards = local_port_forwards
        self.remote_port_forwards = remote_port_forwards
        self.ssh_key_path = ssh_key_path
        self.sync_dirs = sync_dirs
        self.sync_ignore_patterns = sync_ignore_patterns

    @classmethod
    def from_config(cls, config: RemoteDockerConfigProfile):
        instance = AWSInstanceProvider(
            username=INSTANCE_USERNAME,
            project_code=config.project_code,
            aws_region=config.aws_region,
            instance_service_name=config.instance_service_name,
            instance_type=config.instance_type,
            ssh_key_pair_name=config.key_pair_name,
            volume_size=config.volume_size,
        )

        return cls(
            instance=instance,
            local_port_forwards=config.local_port_forwards,
            remote_port_forwards=config.remote_port_forwards,
            ssh_key_path=config.key_path,
            sync_dirs=config.watched_directories,
            sync_ignore_patterns=config.sync_ignore_patterns_git,
        )

    def get_ip(self) -> str:
        logger.debug("Retrieving IP address of instance")
        return self.instance.get_ip()

    def start_instance(self):
        logger.info("Starting instance")
        return self.instance.start_instance()

    def stop_instance(self):
        logger.info("Stopping instance")
        return self.instance.stop_instance()

    def enable_termination_protection(self):
        logger.info("Enabling Termination protection")
        return self.instance.enable_termination_protection()

    def disable_termination_protection(self):
        logger.info("Disabling Termination protection")
        return self.instance.disable_termination_protection()

    def is_termination_protection_enabled(self) -> bool:
        return self.instance.is_termination_protection_enabled()

    def start_tunnel(
        self,
        *,
        extra_local_forwards=None,
        extra_remote_forwards=None,
    ):
        if extra_local_forwards is None:
            extra_local_forwards = {}
        if extra_remote_forwards is None:
            extra_remote_forwards = {}
        local_forwards = dict(self.local_port_forwards, **extra_local_forwards)
        remote_forwards = dict(self.remote_port_forwards, **extra_remote_forwards)

        ip = self.instance.get_ip()
        cmd_s = (
            "sudo ssh -v -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no"
            " -o ServerAliveInterval=60 -N -T"
            f" -i {self.ssh_key_path} {self.instance.username}@{ip}"
        )

        target_sock = "/var/run/remote-docker.sock"
        cmd_s += (
            f" -L {target_sock}:/var/run/docker.sock"
            " -o StreamLocalBindUnlink=yes"
            " -o PermitLocalCommand=yes"
            f" -o LocalCommand='sudo chown {getuser()} {target_sock}'"
        )

        for _name, port_mappings in local_forwards.items():
            for port_from, port_to in port_mappings.items():
                cmd_s += f" -L localhost:{port_from}:localhost:{port_to}"

        for _name, port_mappings in remote_forwards.items():
            for port_from, port_to in port_mappings.items():
                cmd_s += f" -R 0.0.0.0:{port_from}:localhost:{port_to}"

        logger.info("Starting tunnel")
        cmd = shlex.split(cmd_s)
        logger.debug("Running command: %s", cmd_s)

        logger.debug("Forwarding: ")
        logger.debug("Local: %s", self.local_port_forwards)
        logger.debug("Remote: %s", self.remote_port_forwards)
        subprocess.run(cmd, check=True)

    def create_instance(self):
        logger.info("Creating instance")
        return self.instance.create_instance(self.ssh_key_path)

    def delete_instance(self) -> Dict:
        logger.warning("Deleting instance")
        return self.instance.delete_instance()

    def ssh_connect(self, *, ssh_cmd: str = None, options: str = None):
        return self.instance.ssh_connect(
            ssh_key_path=self.ssh_key_path,
            ssh_cmd=ssh_cmd,
            options=options,
        )

    def ssh_run(self, *, ssh_cmd: str):
        return self.instance.ssh_run(
            ssh_key_path=self.ssh_key_path,
            ssh_cmd=ssh_cmd,
        )

    def create_keypair(self) -> Dict:
        return self.instance.create_keypair(self.ssh_key_path)

    def use_remote_context(self):
        logger.info("Switching docker context to remote-docker")

        subprocess.run(
            (
                "docker context inspect remote-docker &>/dev/null || "
                "docker context create"
                " --docker host=unix:///var/run/remote-docker.sock remote-docker"
            ),
            check=True,
            shell=True,
        )
        subprocess.run(
            "docker context use remote-docker >/dev/null",
            check=True,
            shell=True,
        )

    def use_default_context(self):
        logger.info("Switching docker context to default")

        subprocess.run("docker context use default >/dev/null", check=True, shell=True)

    def _get_unison_cmd(
        self,
        *,
        ip: str,
        replica_path: str,
        sync_paths: List[str],
        force: bool = False,
        repeat_watch: bool = False,
    ) -> List[str]:
        cmd_s = (
            f"unison-gitignore {replica_path}"
            f" 'ssh://{self.instance.username}@{ip}/{replica_path}'"
            f" -prefer {replica_path} -batch -sshargs '-i {self.ssh_key_path}'"
        )

        parser = GitIgnoreToUnisonIgnore("/")
        unison_patterns = parser.parse_gitignore(self.sync_ignore_patterns)
        for unison_pattern in unison_patterns:
            cmd_s += f' "{unison_pattern}"'

        for sync_path in sync_paths:
            cmd_s += f" -path {sync_path}"

        if force:
            cmd_s += f" -force {replica_path}"
        if repeat_watch:
            cmd_s += " -repeat watch"

        return shlex.split(cmd_s.replace("\n", ""))

    def sync(
        self,
        *,
        extra_sync_dirs: List[str] = None,
    ):
        if extra_sync_dirs is None:
            extra_sync_dirs = []
        sync_dirs = [
            os.path.expanduser(sync_dir)
            for sync_dir in self.sync_dirs + extra_sync_dirs
        ]

        replica_path, sync_paths = get_replica_and_sync_paths_for_unison(sync_dirs)
        ip = self.get_ip()

        logger.info("Ensuring remote directories exist")
        ssh_cmd_s = (
            f"sudo install -d -o {self.instance.username} -g {self.instance.username}"
        )
        for _dir in sync_dirs:
            ssh_cmd_s += f" -p {_dir}"
        self.ssh_run(ssh_cmd=ssh_cmd_s)

        # First push the local replica's contents to remote
        logger.info("Pushing local files to remote server")
        subprocess.run(
            self._get_unison_cmd(
                ip=ip,
                replica_path=replica_path,
                sync_paths=sync_paths,
                force=True,
            ),
            check=True,
        )

        # Then watch for update
        logger.info("Watching local and remote filesystems for changes")
        watch_cmd = self._get_unison_cmd(
            ip=ip,
            replica_path=replica_path,
            sync_paths=sync_paths,
            repeat_watch=True,
        )

        logger.debug("Watching: %s", sync_dirs)
        logger.debug("Running command: %s", watch_cmd)
        os.execvp(watch_cmd[0], watch_cmd)


def create_remote_docker_client(
    config: RemoteDockerConfigProfile,
) -> RemoteDockerClient:
    return RemoteDockerClient.from_config(config)
