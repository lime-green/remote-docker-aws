from sceptre.cli.helpers import setup_logging

from .cli_commands import cli


def main():
    setup_logging(debug=False, no_colour=False)
    cli()
