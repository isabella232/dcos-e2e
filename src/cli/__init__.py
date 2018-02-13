"""
A CLI for controlling DC/OS clusters on Docker.
"""

import json
import logging
import re
import uuid
from pathlib import Path
from shutil import rmtree
from subprocess import CalledProcessError
from tempfile import gettempdir
from typing import Any, Dict, List, Set, Union  # noqa: F401

import click
import docker
import yaml

from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.distributions import Distribution
from dcos_e2e.docker_storage_drivers import DockerStorageDriver
from dcos_e2e.docker_versions import DockerVersion

logging.disable(logging.WARNING)

_LINUX_DISTRIBUTIONS = {
    'centos-7': Distribution.CENTOS_7,
    'ubuntu-16.04': Distribution.UBUNTU_16_04,
    'coreos': Distribution.COREOS,
    'fedora-23': Distribution.FEDORA_23,
    'debian-8': Distribution.DEBIAN_8,
}

_DOCKER_VERSIONS = {
    '1.13.1': DockerVersion.v1_13_1,
    '1.11.2': DockerVersion.v1_11_2,
}

_DOCKER_STORAGE_DRIVERS = {
    'aufs': DockerStorageDriver.AUFS,
    'overlay': DockerStorageDriver.OVERLAY,
    'overlay2': DockerStorageDriver.OVERLAY_2,
}

_CLUSTER_ID_LABEL_KEY = 'dcos_e2e.cluster_id'
_WORKSPACE_DIR_LABEL_KEY = 'dcos_e2e.workspace_dir'


def _existing_cluster_ids() -> Set[str]:
    """
    Return the IDs of existing clusters.
    """
    client = docker.from_env(version='auto')
    filters = {'label': _CLUSTER_ID_LABEL_KEY}
    containers = client.containers.list(filters=filters)
    return set(
        [container.labels[_CLUSTER_ID_LABEL_KEY] for container in containers]
    )


def _validate_dcos_configuration(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Union[int, bool, str],
) -> Dict[str, Any]:
    """
    Validate that a given value is a YAML map.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    try:
        return dict(yaml.load(str(value)) or {})
    except ValueError:
        message = '"{value}" is not a valid DC/OS configuration'.format(
            value=value,
        )
    except yaml.YAMLError:
        message = '"{value}" is not valid YAML'.format(value=value)

    raise click.BadParameter(message=message)


def _validate_cluster_id(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Union[int, bool, str],
) -> str:
    """
    Validate that a given value is a YAML map.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    if value in _existing_cluster_ids():
        message = 'A cluster with the id "{value}" already exists'.format(
            value=value,
        )
        raise click.BadParameter(message=message)

    # This matches the Docker ID regular expression.
    # This regular expression can be seen by running:
    # > docker run -it --rm --id=' WAT ? I DUNNO ! ' alpine
    if not re.fullmatch('^[a-zA-Z0-9][a-zA-Z0-9_.-]*$', str(value)):
        message = (
            'Invalid cluster id "{value}", only [a-zA-Z0-9][a-zA-Z0-9_.-] '
            'are allowed and the cluster id cannoy be empty'
        ).format(value=value)
        raise click.BadParameter(message)

    return str(value)


def _validate_cluster_exists(
    ctx: click.core.Context,
    param: Union[click.core.Option, click.core.Parameter],
    value: Union[int, bool, str],
) -> str:
    """
    Validate that a cluster exists with the given name.
    """
    # We "use" variables to satisfy linting tools.
    for _ in (ctx, param):
        pass

    cluster_id = str(value)
    if cluster_id not in _existing_cluster_ids():
        message = 'Cluster "{value}" does not exist'.format(value=value)
        raise click.BadParameter(message)

    return cluster_id


@click.group()
def dcos_docker() -> None:
    """
    Manage DC/OS clusters on Docker.
    """


@dcos_docker.command('create')
@click.argument('artifact', type=click.Path(exists=True))
@click.option(
    '--docker-version',
    type=click.Choice(_DOCKER_VERSIONS.keys()),
    default='1.13.1',
    show_default=True,
    help='The Docker version to install on the nodes.',
)
@click.option(
    '--linux-distribution',
    type=click.Choice(_LINUX_DISTRIBUTIONS.keys()),
    default='centos-7',
    show_default=True,
    help='The Linux distribution to use on the nodes.',
)
@click.option(
    '--docker-storage-driver',
    type=click.Choice(_DOCKER_STORAGE_DRIVERS.keys()),
    default=None,
    show_default=False,
    help=(
        'The storage driver to use for Docker in Docker. '
        'By default this uses the host\'s driver.'
    ),
)
@click.option(
    '--masters',
    type=click.INT,
    default=1,
    show_default=True,
    help='The number of master nodes.'
)
@click.option(
    '--agents',
    type=click.INT,
    default=1,
    show_default=True,
    help='The number of agent nodes.'
)
@click.option(
    '--public-agents',
    type=click.INT,
    default=1,
    show_default=True,
    help='The number of public agent nodes.'
)
@click.option(
    '--extra-config',
    type=str,
    default='{}',
    callback=_validate_dcos_configuration,
    help='Extra DC/OS configuration YAML to add to a default configuration.'
)
@click.option(
    '--cluster-id',
    type=str,
    default=uuid.uuid4().hex,
    callback=_validate_cluster_id,
    help='A unique identifier for the cluster. Defaults to a random value.',
)
def create(
    agents: int,
    artifact: str,
    cluster_id: str,
    docker_storage_driver: str,
    docker_version: str,
    extra_config: Dict[str, Any],
    linux_distribution: str,
    masters: int,
    public_agents: int,
) -> None:
    """
    Create a DC/OS cluster.
    """
    custom_master_mounts = {}  # type: Dict[str, Dict[str, str]]
    custom_agent_mounts = {}  # type: Dict[str, Dict[str, str]]
    custom_public_agent_mounts = {}  # type: Dict[str, Dict[str, str]]

    workspace_dir = Path(gettempdir()) / uuid.uuid4().hex

    cluster_backend = Docker(
        custom_master_mounts=custom_master_mounts,
        custom_agent_mounts=custom_agent_mounts,
        custom_public_agent_mounts=custom_public_agent_mounts,
        linux_distribution=_LINUX_DISTRIBUTIONS[linux_distribution],
        docker_version=_DOCKER_VERSIONS[docker_version],
        storage_driver=_DOCKER_STORAGE_DRIVERS.get(docker_storage_driver),
        docker_container_labels={
            _CLUSTER_ID_LABEL_KEY: cluster_id,
            _WORKSPACE_DIR_LABEL_KEY: str(workspace_dir),
        },
        workspace_dir=workspace_dir,
    )

    cluster = Cluster(
        cluster_backend=cluster_backend,
        masters=masters,
        agents=agents,
        public_agents=public_agents,
    )

    try:
        cluster.install_dcos_from_path(
            build_artifact=Path(artifact),
            extra_config=extra_config,
        )
    except CalledProcessError:
        cluster.destroy()
        return

    click.echo(cluster_id)


@dcos_docker.command('list')
def list_clusters() -> None:
    """
    List all clusters.
    """
    for cluster_id in _existing_cluster_ids():
        click.echo(cluster_id)


@dcos_docker.command('destroy')
@click.argument(
    'cluster_ids',
    nargs=-1,
    type=str,
)
def destroy(cluster_ids: List[str]) -> None:
    """
    Destroy a cluster.
    """
    client = docker.from_env(version='auto')

    for cluster_id in cluster_ids:
        filters = {'label': _CLUSTER_ID_LABEL_KEY + '=' + cluster_id}
        containers = client.containers.list(filters=filters)
        if not containers:
            warning = 'Cluster "{cluster_id}" does not exist'.format(
                cluster_id=cluster_id,
            )
            click.echo(warning, err=True)
            continue

        for container in containers:
            workspace_dir = container.labels[_WORKSPACE_DIR_LABEL_KEY]
            container.remove(v=True, force=True)
            rmtree(path=str(workspace_dir), ignore_errors=True)

        click.echo(cluster_id)


@dcos_docker.command('inspect')
@click.argument('cluster_id', type=str, callback=_validate_cluster_exists)
def inspect(cluster_id: str) -> None:
    """
    Show cluster details.
    """
    # client = docker.from_env(version='auto')
    # filters = {'label': _CLUSTER_ID_LABEL_KEY + '=' + cluster_id}
    # containers = client.containers.list(filters=filters)

    # Web address
    # All IP addresses
    # DC/OS version (e.g. Enterprise 1.11)
    data = {
        'Cluster ID': cluster_id,
    }  # type: Dict[Any, Any]
    click.echo(json.dumps(data))


if __name__ == '__main__':
    dcos_docker()
