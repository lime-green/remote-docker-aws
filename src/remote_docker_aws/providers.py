import os
import shlex
import subprocess
import sys
import time
from functools import lru_cache
from typing import Dict

import boto3
from sceptre.context import SceptreContext
from sceptre.plan.plan import SceptrePlan

from .constants import (
    AWS_REGION_TO_UBUNTU_AMI_MAPPING,
    SCEPTRE_PATH,
)
from .exceptions import InstanceNotRunning, RemoteDockerException
from .util import logger, wait_until_port_is_open


@lru_cache()
def _get_ec2_client(region):
    return boto3.client("ec2", region_name=region)


class InstanceProvider:
    def __init__(
        self,
        username: str,
    ):
        self.username = username

    def get_ip(self) -> str:
        raise NotImplementedError

    def create_keypair(self, ssh_key_path: str):
        raise NotImplementedError

    def create_instance(self, ssh_key_path: str):
        raise NotImplementedError

    def delete_instance(self):
        raise NotImplementedError

    def is_running(self):
        raise NotImplementedError

    def is_stopped(self):
        raise NotImplementedError

    def start_instance(self):
        raise NotImplementedError

    def stop_instance(self):
        raise NotImplementedError

    def enable_termination_protection(self):
        raise NotImplementedError

    def disable_termination_protection(self):
        raise NotImplementedError

    def is_termination_protection_enabled(self):
        raise NotImplementedError

    def ssh_connect(
        self, *, ssh_key_path: str, ssh_cmd: str = None, options: str = None
    ):
        cmd = self._build_ssh_cmd(ssh_key_path, ssh_cmd, options)

        os.execvp(cmd[0], cmd)

    def ssh_run(self, *, ssh_key_path: str, ssh_cmd: str = None):
        cmd = self._build_ssh_cmd(ssh_key_path, ssh_cmd)
        return subprocess.run(cmd, check=True)

    def _build_ssh_cmd(self, ssh_key_path: str, ssh_cmd=None, options=None):
        ssh_cmd = ssh_cmd if ssh_cmd else ""
        options = options if options else ""

        cmd_s = (
            f"ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=60"
            f" -i {ssh_key_path}"
            f" {options} {self.username}@{self.get_ip()} {ssh_cmd}"
        )

        logger.debug("Running: %s", cmd_s)
        return shlex.split(cmd_s)


class AWSInstanceProvider(InstanceProvider):
    def __init__(
        self,
        aws_region: str,
        project_code: str,
        instance_service_name: str,
        instance_type: str,
        ssh_key_pair_name: str,
        volume_size: int,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.aws_region = aws_region
        self.project_code = project_code
        self.instance_service_name = instance_service_name
        self.instance_type = instance_type
        self.ssh_key_pair_name = ssh_key_pair_name
        self.volume_size = volume_size

    @property
    def _ec2_client(self):
        return _get_ec2_client(self.aws_region)

    def _search_for_instances(self) -> Dict:
        return self._ec2_client.describe_instances(
            Filters=[dict(Name="tag:service", Values=[self.instance_service_name])]
        )

    def _get_instance(self) -> Dict:
        reservations = self._search_for_instances()["Reservations"]
        valid_reservations = [
            reservation
            for reservation in reservations
            if len(reservation["Instances"]) == 1
            and reservation["Instances"][0]["State"]["Name"] != "terminated"
        ]

        if len(valid_reservations) == 0:
            raise RemoteDockerException(
                "There are no valid reservations, did you create the instance?"
            )
        if len(valid_reservations) > 1:
            raise RemoteDockerException(
                "There is more than one reservation found that matched, not sure what to do"
            )

        instances = valid_reservations[0]["Instances"]
        assert len(instances) == 1, f"{len(instances)} != 1"
        return instances[0]

    def get_ip(self) -> str:
        if not self.is_running():
            raise InstanceNotRunning(
                "Instance is not running. start it with `rd start`"
            )
        return self._get_instance()["PublicIpAddress"]

    def get_instance_id(self) -> str:
        return self._get_instance()["InstanceId"]

    def get_instance_state(self) -> str:
        return self._get_instance()["State"]["Name"]

    def is_running(self):
        return self.get_instance_state() == "running"

    def is_stopped(self):
        return self.get_instance_state() == "stopped"

    def start_instance(self):
        ret = self._ec2_client.start_instances(InstanceIds=[self.get_instance_id()])
        self._wait_for_running_state()
        return ret

    def stop_instance(self):
        ret = self._ec2_client.stop_instances(InstanceIds=[self.get_instance_id()])
        self._wait_for_stopped_state()
        return ret

    def _set_disable_api_termination(self, value: bool):
        return self._ec2_client.modify_instance_attribute(
            DisableApiTermination=dict(Value=value),
            InstanceId=self.get_instance_id(),
        )

    def enable_termination_protection(self):
        return self._set_disable_api_termination(True)

    def disable_termination_protection(self):
        return self._set_disable_api_termination(False)

    def is_termination_protection_enabled(self):
        return self._ec2_client.describe_instance_attribute(
            Attribute="disableApiTermination",
            InstanceId=self.get_instance_id(),
        )["DisableApiTermination"]["Value"]

    def _import_key(self, file_location) -> Dict:
        with open(file_location, "r") as fh:
            file_bytes = fh.read().strip().encode("utf-8")

        self._ec2_client.delete_key_pair(
            KeyName=self.ssh_key_pair_name,
        )
        return self._ec2_client.import_key_pair(
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

    def create_instance(self, ssh_key_path):
        result = self._get_sceptre_plan().create()

        logger.debug("Got sceptre result: %s", result)
        if "complete" not in result.values():
            raise Exception(f"sceptre command failed: {list(result.values())}")
        logger.info("Stack created")

        while self.get_instance_state() != "running":
            logger.warning("Waiting to bootstrap: instance not yet running")
            time.sleep(5)

        logger.info("Waiting until SSH access is available")
        ip = self.get_ip()

        wait_until_port_is_open(ip, 22, sleep_time=3, max_attempts=10)
        # Give it some extra time, AWS can throw fopen errors on apt-get update
        # if this is too rushed
        time.sleep(20)
        logger.info("Starting bootstrap")
        self._bootstrap_instance(ssh_key_path)

    def delete_instance(self) -> Dict:
        result = self._get_sceptre_plan().delete()

        logger.debug("Got sceptre result: %s", result)
        if "complete" not in result.values():
            raise Exception(f"sceptre command failed: {list(result.values())}")
        return result

    # flake8: noqa: E501
    def _bootstrap_instance(self, ssh_key_path: str):
        logger.info("Bootstrapping instance, will take a few minutes")
        configure_instance_cmd_s = """
        set -x
        && sudo sysctl -w net.core.somaxconn=4096
        && sudo apt-get -y update
        && sudo apt-get -y install build-essential curl file git docker.io
        && sudo usermod -aG docker ubuntu
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
        self.ssh_connect(ssh_key_path=ssh_key_path, ssh_cmd=configure_instance_cmd_s)

    def create_keypair(self, ssh_key_path) -> Dict:
        # shell=True with `ssh-keygen` doesn't seem to be passing path correctly
        subprocess.run(
            shlex.split(f"ssh-keygen -t rsa -b 4096 -f {ssh_key_path}"),
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        subprocess.run(
            shlex.split(f"ssh-add -K {ssh_key_path}"),
            check=True,
            stdout=sys.stdout,
            stderr=sys.stderr,
        )
        return self._import_key(
            file_location=f"{ssh_key_path}.pub",
        )

    def _wait_for_running_state(self):
        return self._wait_for_state("running")

    def _wait_for_stopped_state(self):
        return self._wait_for_state("stopped")

    def _wait_for_state(self, desired_state):
        timeout = 120
        step = 5
        elapsed = 0

        while True:
            state = self.get_instance_state()

            if state == desired_state:
                break

            if elapsed >= timeout:
                raise RuntimeError(
                    f"Timed out while waiting for instance to reach {desired_state} state (still in {state})."
                )

            logger.info(f"Waiting for instance to reach {desired_state} state")
            time.sleep(step)
            elapsed += step
