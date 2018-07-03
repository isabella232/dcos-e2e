"""
A CLI for controlling DC/OS clusters on Vagrant.
"""

import logging
from typing import Optional, Union

import click

from .commands.create import create


def _set_logging(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Optional[Union[int, bool, str]],
) -> None:
    """
    Set logging level depending on the chosen verbosity.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    value = min(value, 3)
    value = max(value, 0)
    verbosity_map = {
        0: logging.WARNING,
        1: logging.INFO,
        2: logging.DEBUG,
        3: logging.NOTSET,
    }
    # Disable logging calls of the given severity level or below.
    logging.disable(verbosity_map[int(value or 0)])


@click.option(
    '-v',
    '--verbose',
    count=True,
    callback=_set_logging,
)
@click.group(name='dcos-vagrant')
@click.version_option()
def dcos_vagrant(verbose: None) -> None:
    """
    Manage DC/OS clusters on Vagrant.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (verbose, ):
        pass


dcos_vagrant.add_command(create)