import sys

from sceptre.cli.helpers import setup_logging

from .cli_commands import cli
from .exceptions import RemoteDockerException
from .util import logger


def main():
    setup_logging(debug=False, no_colour=False)

    try:
        cli()
    except RemoteDockerException as e:
        logger.error(e)
        sys.exit(-1)
