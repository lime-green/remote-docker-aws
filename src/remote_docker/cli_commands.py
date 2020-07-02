import click
import os
import sys
from typing import Tuple

from .core import (
    create_keypair,
    get_ip,
    ssh_connect,
    create_instance,
    delete_instance,
    update_instance,
    start_instance,
    stop_instance,
    start_tunnel,
    sync,
)
from .config import RemoteDockerConfigProfile
from .util import logger


pass_config = click.make_pass_decorator(RemoteDockerConfigProfile)


def _convert_port_forward_to_dict(
    config: RemoteDockerConfigProfile, port_forwards: Tuple[str]
):
    if port_forwards is None:
        return None

    ret = {}
    for port_forward in port_forwards:
        port_from, port_to = port_forward.split(":")
        ret[port_from] = port_to
    return ret


@click.group()
@click.option(
    "--profile",
    "profile_name",
    help="Name of the remote-docker profile to use",
    default=None,
)
@click.option(
    "--config-path",
    default="~/.remote-docker.config.json",
    help="Path of the remote-docker JSON config",
)
@click.pass_context
def cli(ctx, profile_name, config_path):
    config = RemoteDockerConfigProfile.from_json_file(config_path, profile_name)

    try:
        aws_profile = config.aws_profile
        os.environ["AWS_PROFILE"] = aws_profile
    except KeyError:
        print(
            "Missing aws_profile config option."
            " Provide via `AWS_PROFILE` env-var or add it to your config"
        )
        sys.exit(1)

    try:
        aws_region = config.aws_region
        os.environ["AWS_REGION"] = aws_region
    except KeyError:
        print(
            "Missing aws_region config option."
            " Provide via `AWS_REGION` env-var or add it to your config"
        )
        sys.exit(1)

    ctx.obj = config
    logger.debug("Config: %s", config)


@cli.command(name="ssh", help="Connect to the remote agent via SSH")
@click.argument("ssh_cmd", required=False)
@click.option("--ssh_options", default=None, help="Pass additional arguments to SSH")
@pass_config
def cmd_ssh(config: RemoteDockerConfigProfile, ssh_options=None, ssh_cmd=None):
    ssh_connect(
        ssh_key_path=config.key_path,
        aws_region=config.aws_region,
        ssh_cmd=ssh_cmd,
        options=ssh_options,
    )


@cli.command(name="start", help="Start the remote agent instance")
@pass_config
def cmd_start(config: RemoteDockerConfigProfile):
    print(start_instance(config.aws_region))


@cli.command(name="stop", help="Stop the remote agent instance")
@pass_config
def cmd_stop(config: RemoteDockerConfigProfile):
    print(stop_instance(config.aws_region))


@cli.command(name="ip", help="Print the IP address of the remote agent")
@pass_config
def cmd_ip(config: RemoteDockerConfigProfile):
    print(get_ip(config.aws_region))


@cli.command(
    name="create-keypair", help="Create and upload a new keypair to AWS for SSH access"
)
@pass_config
def cmd_create_keypair(config: RemoteDockerConfigProfile):
    create_keypair(config.key_path, config.aws_region)


@cli.command(
    name="create", help="Provision a new ec2 instance to use as the remote agent"
)
@pass_config
def cmd_create(config: RemoteDockerConfigProfile):
    print(
        create_instance(
            ssh_key_path=config.key_path,
            aws_region=config.aws_region,
            instance_type=config.instance_type,
        )
    )


@cli.command(name="delete", help="Delete the provisioned ec2 instance")
@pass_config
def cmd_delete(config: RemoteDockerConfigProfile):
    click.confirm("Are you sure you want to delete your instance?", abort=True)
    print(delete_instance(config.aws_region))


@cli.command(name="update", help="Update the provisioned instance")
@pass_config
def cmd_update(config: RemoteDockerConfigProfile):
    print(update_instance(config.aws_region, config.instance_type))


@cli.command(
    name="tunnel",
    help=(
        "Create a SSH tunnel to the remote instance to connect"
        " with the docker agent and containers"
    ),
)
@click.option(
    "--local",
    "-l",
    callback=_convert_port_forward_to_dict,
    multiple=True,
    help="Local port forward: of the form '80:8080'",
)
@click.option(
    "--remote",
    "-r",
    callback=_convert_port_forward_to_dict,
    multiple=True,
    help="Remote port forward: of the form '8080:80'",
)
@pass_config
def cmd_tunnel(config: RemoteDockerConfigProfile, local, remote):
    if local:
        config.add_local_port_forwards("cli_option_local", local)
    if remote:
        config.add_remote_port_forwards("cli_option_remote", remote)

    start_tunnel(
        ssh_key_path=config.key_path,
        local_forwards=config.local_port_forwards,
        remote_forwards=config.remote_port_forwards,
        aws_region=config.aws_region,
    )


@cli.command(name="sync", help="Sync the given directories with the remote instance")
@click.argument("directory", nargs=-1)
@pass_config
def cmd_sync(config: RemoteDockerConfigProfile, directory):
    if directory:
        config.add_watched_directories(directory)
    try:
        config.watched_directories
    except KeyError:
        print("Need at least one directory")
        sys.exit(1)

    sync(
        dirs=config.watched_directories,
        ssh_key_path=config.key_path,
        sync_ignore_patterns_git=config.sync_ignore_patterns_git,
        aws_region=config.aws_region,
    )
