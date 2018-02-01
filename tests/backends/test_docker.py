"""
Tests for the Docker backend.
"""

import uuid
from pathlib import Path

# See https://github.com/PyCQA/pylint/issues/1536 for details on why the errors
# are disabled.
import pytest
from py.path import local  # pylint: disable=no-name-in-module, import-error

from dcos_e2e.backends import Docker
from dcos_e2e.cluster import Cluster
from dcos_e2e.distributions import Distribution
from dcos_e2e.node import Node


class TestDockerBackend:
    """
    Tests for functionality specific to the Docker backend.
    """

    def test_custom_mounts(self, tmpdir: local) -> None:
        """
        It is possible to mount local files to master nodes.
        """
        local_master_file = tmpdir.join('master_file.txt')
        local_master_file.write('')
        local_agent_file = tmpdir.join('agent_file.txt')
        local_agent_file.write('')
        local_public_agent_file = tmpdir.join('public_agent_file.txt')
        local_public_agent_file.write('')

        master_path = Path('/etc/on_master_nodes.txt')
        agent_path = Path('/etc/on_agent_nodes.txt')
        public_agent_path = Path('/etc/on_public_agent_nodes.txt')

        custom_master_mounts = {
            str(local_master_file): {
                'bind': str(master_path),
                'mode': 'rw',
            },
        }

        custom_agent_mounts = {
            str(local_agent_file): {
                'bind': str(agent_path),
                'mode': 'rw',
            },
        }

        custom_public_agent_mounts = {
            str(local_public_agent_file): {
                'bind': str(public_agent_path),
                'mode': 'rw',
            },
        }

        backend = Docker(
            custom_master_mounts=custom_master_mounts,
            custom_agent_mounts=custom_agent_mounts,
            custom_public_agent_mounts=custom_public_agent_mounts,
        )

        with Cluster(
            cluster_backend=backend,
            masters=1,
            agents=1,
            public_agents=1,
        ) as cluster:
            for nodes, path, local_file in [
                (cluster.masters, master_path, local_master_file),
                (cluster.agents, agent_path, local_agent_file),
                (
                    cluster.public_agents, public_agent_path,
                    local_public_agent_file
                ),
            ]:
                for node in nodes:
                    content = str(uuid.uuid4())
                    local_file.write(content)
                    args = ['cat', str(path)]
                    result = node.run(args=args, user=cluster.default_ssh_user)
                    assert result.stdout.decode() == content

    def test_install_dcos_from_url(self, oss_artifact_url: str) -> None:
        """
        The Docker backend requires a build artifact in order
        to launch a DC/OS cluster.
        """
        with Cluster(
            cluster_backend=Docker(),
            masters=1,
            agents=0,
            public_agents=0,
        ) as cluster:
            with pytest.raises(NotImplementedError) as excinfo:
                cluster.install_dcos_from_url(oss_artifact_url)

        expected_error = (
            'The Docker backend does not support the installation of DC/OS '
            'by build artifacts passed via URL string. This is because a more '
            'efficient installation method exists in `install_dcos_from_path`.'
        )

        assert str(excinfo.value) == expected_error


class TestDistributions:
    """
    Tests for setting distributions.
    """

    def _get_node_distribution(
        self,
        node: Node,
        default_ssh_user: str,
    ) -> Distribution:
        """
        Given a `Node`, return the `Distribution` on that node.
        """
        cat_cmd = node.run(
            args=['cat /etc/*-release'],
            user=default_ssh_user,
            shell=True,
        )

        version_info = cat_cmd.stdout
        version_info_lines = [
            line for line in version_info.decode().split('\n') if '=' in line
        ]
        version_data = dict(item.split('=') for item in version_info_lines)

        distributions = {
            ('"centos"', '"7"'): Distribution.CENTOS_7,
            ('ubuntu', '"16.04"'): Distribution.UBUNTU_16_04,
            ('coreos', '12.98.7.0'): Distribution.COREOS,
            ('fedora', '23'): Distribution.FEDORA_23,
            ('debian', '"8"'): Distribution.DEBIAN_8,
        }

        return distributions[(version_data['ID'], version_data['VERSION_ID'])]

    def test_default(self) -> None:
        """
        The default Linux distribution for a `Node`s is the default Linux
        distribution of the backend.
        """
        with Cluster(
            cluster_backend=Docker(),
            masters=1,
            agents=0,
            public_agents=0,
        ) as cluster:
            (master, ) = cluster.masters
            node_distribution = self._get_node_distribution(
                node=master,
                default_ssh_user=cluster.default_ssh_user,
            )

        assert node_distribution == Distribution.CENTOS_7

    @pytest.mark.parametrize(
        'unsupported_linux_distribution',
        set(Distribution) - {Distribution.CENTOS_7}
    )
    def test_custom_choice(
        self,
        unsupported_linux_distribution: Distribution,
    ) -> None:
        """
        Starting a cluster with a non-default Linux distribution raises a
        `NotImplementedError`.
        """
        with pytest.raises(NotImplementedError):
            Docker(linux_distribution=unsupported_linux_distribution)
