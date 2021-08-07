import click
from typing import Tuple

from .core import (
    create_remote_docker_client,
    RemoteDockerClient,
)
from .config import RemoteDockerConfigProfile
from .util import logger


CLICK_CONTEXT_SETTINGS = dict(
    # Don't cutoff command help docs
    max_content_width=500,
)
pass_config = click.make_pass_decorator(RemoteDockerClient)


def _convert_port_forward_to_dict(
    _ctx, _client: RemoteDockerClient, port_forwards: Tuple[str]
):
    if port_forwards is None:
        return None

    ret = {}
    for port_forward in port_forwards:
        port_from, port_to = port_forward.split(":")
        ret[port_from] = port_to
    return dict(cli_port_forward=ret)


@click.group(context_settings=CLICK_CONTEXT_SETTINGS)
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
    logger.debug("Config: %s", config)
    ctx.obj = create_remote_docker_client(config)


@cli.command(name="ssh")
@click.argument("ssh_cmd", required=False)
@click.option("--ssh_options", default=None, help="Pass additional arguments to SSH")
@pass_config
def cmd_ssh(client: RemoteDockerClient, ssh_options=None, ssh_cmd=None):
    """Connect to the remote agent via SSH"""
    client.ssh_connect(ssh_cmd=ssh_cmd, options=ssh_options)


@cli.command(name="start")
@pass_config
def cmd_start(client: RemoteDockerClient):
    """Start the remote agent instance"""
    print(client.start_instance())
    client.use_remote_context()


@cli.command(name="stop")
@pass_config
def cmd_stop(client: RemoteDockerClient):
    """Stop the remote agent instance"""
    print(client.stop_instance())
    client.use_default_context()


@cli.command(name="ip")
@pass_config
def cmd_ip(client: RemoteDockerClient):
    """Print the IP address of the remote agent"""
    print(client.get_ip())


@cli.command(name="create-keypair")
@pass_config
def cmd_create_keypair(client: RemoteDockerClient):
    """Create and upload a new keypair to AWS for SSH access"""
    client.create_keypair()


@cli.command(name="create")
@pass_config
def cmd_create(client: RemoteDockerClient):
    """Provision a new ec2 instance to use as the remote agent"""
    print(client.create_instance())
    client.use_remote_context()


@cli.command(name="delete")
@pass_config
def cmd_delete(client: RemoteDockerClient):
    """Delete the provisioned ec2 instance"""
    if client.is_termination_protection_enabled():
        raise click.exceptions.ClickException(
            "Termination protection is currently enabled."
            " It first must be disabled to delete the instance"
        )

    click.confirm("Are you sure you want to delete your instance?", abort=True)
    print(client.delete_instance())
    client.use_default_context()


@cli.command(
    name="tunnel",
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
    """
    Create a SSH tunnel to the remote instance to connect
    with the docker agent and containers
    """
    client.start_tunnel(extra_local_forwards=local, extra_remote_forwards=remote)


@cli.command(name="sync")
@click.argument("directories", nargs=-1)
@pass_config
def cmd_sync(client: RemoteDockerClient, directories: Tuple[str]):
    """Sync the given directories with the remote instance"""
    client.sync(extra_sync_dirs=list(directories))


@cli.command(
    name="disable-termination-protection",
)
@pass_config
def disable_termination_protection(client: RemoteDockerClient):
    """
    Turns off termination protection,
    thereby allowing your instance to be deleted
    """
    client.disable_termination_protection()


@cli.command(
    name="enable-termination-protection",
)
@pass_config
def enable_termination_protection(client: RemoteDockerClient):
    """
    Prevents your instance from being deleted through
    the API and AWS console GUI"
    """
    client.enable_termination_protection()


@cli.command(
    name="context",
)
@pass_config
def use_remote_context(client: RemoteDockerClient):
    """
    Creates and switches to the remote-docker context
    """
    client.use_remote_context()
