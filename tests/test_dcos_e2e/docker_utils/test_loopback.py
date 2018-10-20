import uuid

import docker
import pytest

from dcos_e2e.docker_utils import DockerLoopbackVolume


class TestDockerLoopbackVolume:
    """
    Tests for setting device mapping on master or agent Docker containers.
    """

    def test_loopback(self) -> None:
        """
        An instance of ``DockerLoopbackVolume`` provides a container which can
        access a block device.
        """
        client = docker.from_env(version='auto')

        with DockerLoopbackVolume(size=1) as device:
            block_device_exists_cmd = ['lsblk', device.path]
            exit_code, output = device.container.exec_run(
                cmd=block_device_exists_cmd,
            )

            assert exit_code == 0, device.path + ': ' + output.decode()

        new_container_2 = client.containers.create(
            privileged=True,
            detach=True,
            tty=True,
            image='centos:7',
        )
        new_container_2.start()
        exit_code, output = new_container_2.exec_run(
            cmd=block_device_exists_cmd,
        )

        # TODO new container can access this
        assert exit_code == 1

    def test_labels(self) -> None:
        """
        The given labels are applied to the new container.
        """
        labels = {uuid.uuid4().hex: uuid.uuid4().hex}

        with DockerLoopbackVolume(size=1, labels=labels) as device:
            for key, value in labels.items():
                assert device.container.labels[key] == value

    def test_multiple(self) -> None:
        """
        Multiple sidecars can exist at once.
        """
        with DockerLoopbackVolume(size=1) as first:
            with DockerLoopbackVolume(size=1) as second:
                assert first.path != second.path
                assert first.container != second.container

    def test_accessible_multiple_containers(self) -> None:
        """
        The block device created is accessible to multiple containers.
        """
        client = docker.from_env(version='auto')

        with DockerLoopbackVolume(size=1) as device:
            block_device_exists_cmd = ['lsblk', device.path]
            new_container = client.containers.create(
                privileged=True,
                detach=True,
                tty=True,
                image='centos:7',
            )
            new_container.start()
            exit_code, output = new_container.exec_run(
                cmd=block_device_exists_cmd,
            )

            assert exit_code == 0, device.path + ': ' + output.decode()

    def test_destroy(self) -> None:
        """
        The container and block device are destroyed.
        """
        client = docker.from_env(version='auto')

        with DockerLoopbackVolume(size=1) as device:
            existing_container = device.container
            block_device_exists_cmd = ['lsblk', device.path]

        with pytest.raises(docker.errors.NotFound):
            existing_container.reload()

        new_container = client.containers.create(
            privileged=True,
            detach=True,
            tty=True,
            image='centos:7',
        )
        new_container.start()
        exit_code, output = new_container.exec_run(
            cmd=block_device_exists_cmd,
        )

        import pdb; pdb.set_trace()
        assert exit_code == 1, output.decode()
        # TODO new container

    # TODO destroy new container
    # TODO update CLI
    # TODO remove tty in tests and implementation
    # TODO test size
