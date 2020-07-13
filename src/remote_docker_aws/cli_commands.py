import click
import os
from typing import Tuple

from .core import (
    create_remote_docker_client,
    RemoteDockerClient,
)
from .config import RemoteDockerConfigProfile
from .util import logger


pass_config = click.make_pass_decorator(RemoteDockerClient)


def _convert_port_forward_to_dict(
    _client: RemoteDockerClient, port_forwards: Tuple[str]
):
    if port_forwards is None:
        return None

    ret = {}
    for port_forward in port_forwards:
        port_from, port_to = port_forward.split(":")
        ret[port_from] = port_to
    return dict(cli_port_forward=ret)


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
        pass

    try:
        aws_region = config.aws_region
        os.environ["AWS_REGION"] = aws_region
    except KeyError:
        pass

    logger.debug("Config: %s", config)
    ctx.obj = create_remote_docker_client(config)


@cli.command(name="ssh", help="Connect to the remote agent via SSH")
@click.argument("ssh_cmd", required=False)
@click.option("--ssh_options", default=None, help="Pass additional arguments to SSH")
@pass_config
def cmd_ssh(client: RemoteDockerClient, ssh_options=None, ssh_cmd=None):
    client.ssh_connect(ssh_cmd=ssh_cmd, options=ssh_options)


@cli.command(name="start", help="Start the remote agent instance")
@pass_config
def cmd_start(client: RemoteDockerClient):
    print(client.start_instance())


@cli.command(name="stop", help="Stop the remote agent instance")
@pass_config
def cmd_stop(client: RemoteDockerClient):
    print(client.stop_instance())


@cli.command(name="ip", help="Print the IP address of the remote agent")
@pass_config
def cmd_ip(client: RemoteDockerClient):
    print(client.get_ip())


@cli.command(
    name="create-keypair", help="Create and upload a new keypair to AWS for SSH access"
)
@pass_config
def cmd_create_keypair(client: RemoteDockerClient):
    client.create_keypair()


@cli.command(
    name="create", help="Provision a new ec2 instance to use as the remote agent"
)
@pass_config
def cmd_create(client: RemoteDockerClient):
    print(client.create_instance())


@cli.command(name="delete", help="Delete the provisioned ec2 instance")
@pass_config
def cmd_delete(client: RemoteDockerClient):
    click.confirm("Are you sure you want to delete your instance?", abort=True)
    print(client.delete_instance())


@cli.command(name="update", help="Update the provisioned instance")
@pass_config
def cmd_update(client: RemoteDockerClient):
    print(client.update_instance())


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
def cmd_tunnel(client: RemoteDockerClient, local, remote):
    client.start_tunnel(extra_local_forwards=local, extra_remote_forwards=remote)


@cli.command(name="sync", help="Sync the given directories with the remote instance")
@click.argument("directories", nargs=-1)
@pass_config
def cmd_sync(client: RemoteDockerClient, directories: Tuple[str]):
    client.sync(extra_sync_dirs=list(directories))
