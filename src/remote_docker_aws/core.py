import os
import pathlib
import shlex
import subprocess
import sys
import time
from functools import lru_cache
from typing import Dict, List

import boto3
from sceptre.context import SceptreContext
from sceptre.plan.plan import SceptrePlan
from unison_gitignore.parser import GitIgnoreToUnisonIgnore

from .constants import (
    AWS_REGION_TO_UBUNTU_AMI_MAPPING,
    DOCKER_PORT_FORWARD,
    KEY_PAIR_NAME,
    INSTANCE_SERVICE_NAME,
    INSTANCE_USERNAME,
    PORT_MAP_TYPE,
)
from .util import get_replica_and_sync_paths_for_unison, logger, wait_until_port_is_open


@lru_cache(maxsize=128)
def get_ec2_client(region_name):
    return boto3.client("ec2", region_name=region_name)


def search_for_instances(aws_region) -> Dict:
    return get_ec2_client(aws_region).describe_instances(
        Filters=[dict(Name="tag:service", Values=[INSTANCE_SERVICE_NAME])]
    )


def get_instance(aws_region) -> Dict:
    reservations = search_for_instances(aws_region)["Reservations"]
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


def get_ip(aws_region) -> str:
    logger.info("Retrieving IP address of instance")
    return get_instance(aws_region)["PublicIpAddress"]


def get_instance_id(aws_region) -> str:
    return get_instance(aws_region)["InstanceId"]


def get_instance_state(aws_region) -> str:
    return get_instance(aws_region)["State"]["Name"]


def start_instance(aws_region):
    logger.warning("Starting instance")
    return get_ec2_client(aws_region).start_instances(
        InstanceIds=[get_instance_id(aws_region)]
    )


def stop_instance(aws_region):
    logger.warning("Stopping instance")
    return get_ec2_client(aws_region).stop_instances(
        InstanceIds=[get_instance_id(aws_region)]
    )


def start_tunnel(
    *,
    ssh_key_path: str,
    local_forwards: PORT_MAP_TYPE,
    remote_forwards: PORT_MAP_TYPE,
    aws_region: str,
):
    ip = get_ip(aws_region)
    cmd_s = f"""
    sudo ssh -v -o StrictHostKeyChecking=no -o "ServerAliveInterval=60" -N -T
     -i {ssh_key_path} {INSTANCE_USERNAME}@{ip}
    """

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
    logger.warning("Local: %s", local_forwards)
    logger.warning("Remote: %s", remote_forwards)
    subprocess.run(cmd)


def import_key(name, file_location, aws_region) -> Dict:
    with open(file_location, "r") as fh:
        file_bytes = fh.read().strip().encode("utf-8")

    return get_ec2_client(aws_region).import_key_pair(
        KeyName=name,
        # Documentation is lying, shouldn't be b64 encoded...
        PublicKeyMaterial=file_bytes,
    )


def _get_sceptre_plan(region: str, instance_type: str = None) -> SceptrePlan:
    sceptre_path = os.path.join(pathlib.Path(__file__).parent.absolute(), "sceptre")
    context = SceptreContext(
        sceptre_path,
        "dev/application.yaml",
        user_variables=dict(
            key_pair_name=KEY_PAIR_NAME,
            image_id=AWS_REGION_TO_UBUNTU_AMI_MAPPING[region],
            instance_type=instance_type,
            region=region,
            service_name=INSTANCE_SERVICE_NAME,
        ),
    )
    return SceptrePlan(context)


def create_instance(*, ssh_key_path: str, aws_region: str, instance_type: str):
    logger.warning("Creating instance")
    result = _get_sceptre_plan(aws_region, instance_type).create()

    logger.debug("Got sceptre result: %s", result)
    if "complete" not in result.values():
        raise Exception(f"sceptre command failed: {list(result.values())}")
    logger.warning("Stack created")

    while get_instance_state(aws_region) != "running":
        logger.warning("Waiting to bootstrap: instance not yet running")
        time.sleep(5)

    logger.warning("Waiting until SSH access is available")
    ip = get_ip(aws_region)

    wait_until_port_is_open(ip, 22, sleep_time=3, max_attempts=10)
    # Give it some extra time, AWS can throw fopen errors on apt-get update
    # if this is too rushed
    time.sleep(15)
    logger.warning("Starting bootstrap")
    bootstrap_instance(ssh_key_path=ssh_key_path, aws_region=aws_region)


def update_instance(region: str, instance_type: str = None) -> Dict:
    logger.warning("Updating instance")
    result = _get_sceptre_plan(region, instance_type).update()

    logger.debug("Got sceptre result: %s", result)
    if "complete" not in result.values():
        raise Exception(f"sceptre command failed: {list(result.values())}")
    return result


def delete_instance(region: str) -> Dict:
    logger.warning("Deleting instance")
    result = _get_sceptre_plan(region).delete()

    logger.debug("Got sceptre result: %s", result)
    if "complete" not in result.values():
        raise Exception(f"sceptre command failed: {list(result.values())}")
    return result


# flake8: noqa: E501
def bootstrap_instance(ssh_key_path, aws_region):
    logger.warning("Bootstrapping instance, will take a few minutes")
    configure_instance_cmd_s = """
    set -x
    && sudo apt-get -y update
    && sudo apt-get -y install build-essential curl file git docker.io
    && "sudo sed -i -e '/ExecStart=/ s/fd:\/\//127\.0\.0\.1:2375/' '/lib/systemd/system/docker.service'"
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
    ssh_connect(
        ssh_key_path=ssh_key_path,
        aws_region=aws_region,
        ssh_cmd=configure_instance_cmd_s,
    )


def _build_ssh_cmd(ssh_key_path, ip, ssh_cmd=None, options=None):
    ssh_cmd = ssh_cmd if ssh_cmd else ""
    options = options if options else ""

    cmd_s = f"""
    ssh -o StrictHostKeyChecking=no -i {ssh_key_path}
    {options} {INSTANCE_USERNAME}@{ip} {ssh_cmd}
    """

    return shlex.split(cmd_s)


def ssh_connect(
    *, ssh_key_path: str, aws_region: str, ssh_cmd: str = None, options: str = None
):
    ip = get_ip(aws_region)
    cmd = _build_ssh_cmd(ssh_key_path, ip, ssh_cmd, options)

    os.execvp(cmd[0], cmd)


def ssh_run(*, ssh_key_path: str, ip: str, ssh_cmd: str):
    cmd = _build_ssh_cmd(ssh_key_path, ip, ssh_cmd)

    p = subprocess.run(cmd)
    p.check_returncode()


def create_keypair(ssh_key_path: str, aws_region: str) -> Dict:
    path = ssh_key_path
    p = subprocess.run(
        shlex.split(f"ssh-keygen -t rsa -b 4096 -f {path}"),
        shell=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    p.check_returncode()
    p = subprocess.run(
        shlex.split(f"ssh-add -K {path}"),
        shell=True,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    p.check_returncode()
    return import_key(
        aws_region=aws_region, name=KEY_PAIR_NAME, file_location=f"{path}.pub",
    )


def get_unison_cmd(
    replica_path: str,
    sync_paths: List[str],
    ssh_key_path: str,
    sync_ignore_patterns: List[str],
    ip: str,
    force: bool = False,
    repeat_watch: bool = False,
) -> List[str]:
    cmd_s = f"""
    unison-gitignore {replica_path} 'ssh://{INSTANCE_USERNAME}@{ip}/{replica_path}'
    -prefer {replica_path} -batch -sshargs '-i {ssh_key_path}'
    """

    parser = GitIgnoreToUnisonIgnore("/")
    unison_patterns = parser.parse_gitignore(sync_ignore_patterns)
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
    *,
    dirs: List[str],
    ssh_key_path: str,
    sync_ignore_patterns_git: List[str],
    aws_region: str,
):
    replica_path, sync_paths = get_replica_and_sync_paths_for_unison(dirs)
    ip = get_ip(aws_region)

    logger.warning("Ensuring remote directories exist")
    ssh_cmd_s = f"sudo install -d -o {INSTANCE_USERNAME} -g {INSTANCE_USERNAME}"
    for _dir in dirs:
        ssh_cmd_s += f" -p {_dir}"
    ssh_run(ssh_key_path=ssh_key_path, ip=ip, ssh_cmd=ssh_cmd_s)

    # First push the local replica's contents to remote
    logger.info("Pushing local files to remote server")
    subprocess.run(
        get_unison_cmd(
            replica_path,
            sync_paths,
            ssh_key_path,
            sync_ignore_patterns_git,
            ip=ip,
            force=True,
        )
    )

    # Then watch for update
    logger.info("Watching local and remote filesystems for changes")
    watch_cmd = get_unison_cmd(
        replica_path,
        sync_paths,
        ssh_key_path,
        sync_ignore_patterns_git,
        ip=ip,
        repeat_watch=True,
    )

    logger.warning("")
    logger.warning("Watching: %s", dirs)
    logger.debug("Running command :%s", watch_cmd)
    os.execvp(watch_cmd[0], watch_cmd)
