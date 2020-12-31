import os
import shlex
import subprocess
import sys
import time
from functools import lru_cache
from typing import Dict, List

import boto3
from sceptre.cli.helpers import setup_logging
from sceptre.context import SceptreContext
from sceptre.plan.plan import SceptrePlan
from unison_gitignore.parser import GitIgnoreToUnisonIgnore

from .config import RemoteDockerConfigProfile
from .constants import (
    AWS_REGION_TO_UBUNTU_AMI_MAPPING,
    DOCKER_PORT_FORWARD,
    INSTANCE_USERNAME,
    PORT_MAP_TYPE,
    SCEPTRE_PATH,
)
from .util import get_replica_and_sync_paths_for_unison, logger, wait_until_port_is_open


setup_logging(debug=False, no_colour=False)


@lru_cache(maxsize=128)
def get_ec2_client(region_name):
    return boto3.client("ec2", region_name=region_name)


class RemoteDockerClient:
    def __init__(
        self,
        project_code: str,
        aws_region: str,
        instance_service_name: str,
        instance_type: str,
        local_forwards: PORT_MAP_TYPE,
        remote_forwards: PORT_MAP_TYPE,
        ssh_key_path: str,
        ssh_key_pair_name: str,
        sync_dirs: List[str],
        sync_ignore_patterns: List[str],
        volume_size: int,
    ):
        self.project_code = project_code
        self.aws_region = aws_region
        self.instance_service_name = instance_service_name
        self.instance_type = instance_type
        self.local_forwards = local_forwards
        self.remote_forwards = remote_forwards
        self.ssh_key_path = ssh_key_path
        self.ssh_key_pair_name = ssh_key_pair_name
        self.sync_dirs = sync_dirs
        self.sync_ignore_patterns = sync_ignore_patterns
        self.volume_size = volume_size

    @classmethod
    def from_config(cls, config: RemoteDockerConfigProfile):
        return cls(
            project_code=config.project_code,
            aws_region=config.aws_region,
            instance_service_name=config.instance_service_name,
            instance_type=config.instance_type,
            local_forwards=config.local_port_forwards,
            remote_forwards=config.remote_port_forwards,
            ssh_key_path=config.key_path,
            ssh_key_pair_name=config.key_pair_name,
            sync_dirs=config.watched_directories,
            sync_ignore_patterns=config.sync_ignore_patterns_git,
            volume_size=config.volume_size,
        )

    @property
    def ec2_client(self):
        return get_ec2_client(region_name=self.aws_region)

    def search_for_instances(self) -> Dict:
        return self.ec2_client.describe_instances(
            Filters=[dict(Name="tag:service", Values=[self.instance_service_name])]
        )

    def get_instance(self) -> Dict:
        reservations = self.search_for_instances()["Reservations"]
        valid_reservations = [
            reservation
            for reservation in reservations
            if len(reservation["Instances"]) == 1
            and reservation["Instances"][0]["State"]["Name"] != "terminated"
        ]

        if len(valid_reservations) == 0:
            raise RuntimeError(
                "There are no valid reservations, did you create the instance?"
            )
        if len(valid_reservations) > 1:
            raise RuntimeError(
                "There is more than one reservation found that matched, not sure what to do"
            )

        instances = valid_reservations[0]["Instances"]
        assert len(instances) == 1, f"{len(instances)} != 1"
        return instances[0]

    def get_ip(self) -> str:
        logger.info("Retrieving IP address of instance")
        return self.get_instance()["PublicIpAddress"]

    def get_instance_id(self) -> str:
        return self.get_instance()["InstanceId"]

    def get_instance_state(self) -> str:
        return self.get_instance()["State"]["Name"]

    def start_instance(self):
        logger.warning("Starting instance")
        return self.ec2_client.start_instances(InstanceIds=[self.get_instance_id()])

    def stop_instance(self):
        logger.warning("Stopping instance")
        return self.ec2_client.stop_instances(InstanceIds=[self.get_instance_id()])

    def _set_disable_api_termination(self, value: bool):
        return self.ec2_client.modify_instance_attribute(
            DisableApiTermination=dict(Value=value),
            InstanceId=self.get_instance_id(),
        )

    def enable_termination_protection(self):
        logger.warning("Enabling Termination protection")
        return self._set_disable_api_termination(True)

    def disable_termination_protection(self):
        logger.warning("Disabling Termination protection")
        return self._set_disable_api_termination(False)

    def is_termination_protection_enabled(self):
        return self.ec2_client.describe_instance_attribute(
            Attribute="disableApiTermination",
            InstanceId=self.get_instance_id(),
        )["DisableApiTermination"]["Value"]

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
        local_forwards = dict(self.local_forwards, **extra_local_forwards)
        remote_forwards = dict(self.remote_forwards, **extra_remote_forwards)

        ip = self.get_ip()
        cmd_s = (
            "sudo ssh -v -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no"
            ' -o "ServerAliveInterval=60" -N -T'
            f" -i {self.ssh_key_path} {INSTANCE_USERNAME}@{ip}"
        )

        for port_from, port_to in DOCKER_PORT_FORWARD.items():
            cmd_s += f" -L localhost:{port_from}:localhost:{port_to}"

        for _name, port_mappings in local_forwards.items():
            for port_from, port_to in port_mappings.items():
                cmd_s += f" -L localhost:{port_from}:localhost:{port_to}"

        for _name, port_mappings in remote_forwards.items():
            for port_from, port_to in port_mappings.items():
                cmd_s += f" -R 0.0.0.0:{port_from}:localhost:{port_to}"

        logger.warning("Starting tunnel")
        cmd = shlex.split(cmd_s)
        logger.debug("Running cmd: %s", cmd)

        logger.warning("")
        logger.warning("Forwarding: ")
        logger.warning("Local: %s", self.local_forwards)
        logger.warning("Remote: %s", self.remote_forwards)
        # Use `subprocess.run` instead of `os.execvp` because the latter
        # prints a strange error: `sudo: setrlimit(RLIMIT_STACK): Invalid argument`
        subprocess.run(cmd, check=True)

    def import_key(self, file_location) -> Dict:
        with open(file_location, "r") as fh:
            file_bytes = fh.read().strip().encode("utf-8")

        self.ec2_client.delete_key_pair(
            KeyName=self.ssh_key_pair_name,
        )
        return self.ec2_client.import_key_pair(
            KeyName=self.ssh_key_pair_name,
            # Documentation is lying, shouldn't be b64 encoded...
            PublicKeyMaterial=file_bytes,
        )

    def _get_sceptre_plan(self) -> SceptrePlan:
        context = SceptreContext(
            SCEPTRE_PATH,
            "dev/application.yaml",
            user_variables=dict(
                key_pair_name=self.ssh_key_pair_name,
                image_id=AWS_REGION_TO_UBUNTU_AMI_MAPPING[self.aws_region],
                instance_type=self.instance_type,
                project_code=self.project_code,
                region=self.aws_region,
                service_name=self.instance_service_name,
                volume_size=int(self.volume_size),
            ),
        )
        return SceptrePlan(context)

    def create_instance(self):
        logger.warning("Creating instance")
        result = self._get_sceptre_plan().create()

        logger.debug("Got sceptre result: %s", result)
        if "complete" not in result.values():
            raise Exception(f"sceptre command failed: {list(result.values())}")
        logger.warning("Stack created")

        while self.get_instance_state() != "running":
            logger.warning("Waiting to bootstrap: instance not yet running")
            time.sleep(5)

        logger.warning("Waiting until SSH access is available")
        ip = self.get_ip()

        wait_until_port_is_open(ip, 22, sleep_time=3, max_attempts=10)
        # Give it some extra time, AWS can throw fopen errors on apt-get update
        # if this is too rushed
        time.sleep(15)
        logger.warning("Starting bootstrap")
        self.bootstrap_instance()

    def delete_instance(self) -> Dict:
        logger.warning("Deleting instance")
        result = self._get_sceptre_plan().delete()

        logger.debug("Got sceptre result: %s", result)
        if "complete" not in result.values():
            raise Exception(f"sceptre command failed: {list(result.values())}")
        return result

    def _build_ssh_cmd(self, ssh_cmd=None, options=None):
        ssh_cmd = ssh_cmd if ssh_cmd else ""
        options = options if options else ""

        cmd_s = (
            f"ssh -o StrictHostKeyChecking=no -i {self.ssh_key_path}"
            f" {options} {INSTANCE_USERNAME}@{self.get_ip()} {ssh_cmd}"
        )

        return shlex.split(cmd_s)

    def ssh_connect(self, *, ssh_cmd: str = None, options: str = None):
        cmd = self._build_ssh_cmd(ssh_cmd, options)

        os.execvp(cmd[0], cmd)

    def ssh_run(self, *, ssh_cmd: str):
        cmd = self._build_ssh_cmd(ssh_cmd)
        return subprocess.run(cmd, check=True)

    # flake8: noqa: E501
    def bootstrap_instance(self):
        logger.warning("Bootstrapping instance, will take a few minutes")
        configure_instance_cmd_s = """
        set -x
        && sudo sysctl -w net.core.somaxconn=4096
        && sudo apt-get -y update
        && sudo apt-get -y install build-essential curl file git docker.io
        && "sudo sed -i -e '/ExecStart=/ s/fd:\/\//127\.0\.0\.1:2375/' '/lib/systemd/system/docker.service'"
        && sudo cp /lib/systemd/system/docker.service /etc/systemd/system/docker.service
        && sudo systemctl daemon-reload
        && sudo systemctl restart docker.service
        && sudo systemctl enable docker.service
        && "sudo sed -i -e '/GatewayPorts/ s/^.*$/GatewayPorts yes/' '/etc/ssh/sshd_config'"
        && sudo service sshd restart
        && /bin/bash -c '"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install.sh)"'
        && eval $(/home/linuxbrew/.linuxbrew/bin/brew shellenv)
        && echo 'eval $(/home/linuxbrew/.linuxbrew/bin/brew shellenv)' >> /home/ubuntu/.profile
        && brew install unison eugenmayer/dockersync/unox
        && sudo cp "$(which unison)" /usr/local/bin/
        && sudo cp "$(which unison-fsmonitor)" /usr/local/bin/
        """
        self.ssh_connect(ssh_cmd=configure_instance_cmd_s)

    def create_keypair(self) -> Dict:
        path = self.ssh_key_path
        # shell=True with `ssh-keygen` doesn't seem to be passing path correctly
        subprocess.run(
            shlex.split(f"ssh-keygen -t rsa -b 4096 -f {path}"),
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        subprocess.run(
            shlex.split(f"ssh-add -K {path}"),
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return self.import_key(
            file_location=f"{path}.pub",
        )

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
            f"unison-gitignore {replica_path} 'ssh://{INSTANCE_USERNAME}@{ip}/{replica_path}'"
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

        logger.warning("Ensuring remote directories exist")
        ssh_cmd_s = f"sudo install -d -o {INSTANCE_USERNAME} -g {INSTANCE_USERNAME}"
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

        logger.warning("")
        logger.warning("Watching: %s", sync_dirs)
        logger.debug("Running command :%s", watch_cmd)
        os.execvp(watch_cmd[0], watch_cmd)


def create_remote_docker_client(
    config: RemoteDockerConfigProfile,
) -> RemoteDockerClient:
    return RemoteDockerClient.from_config(config)
