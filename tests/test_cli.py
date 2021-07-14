import os
import subprocess
from contextlib import contextmanager
from unittest import mock

import pytest
from click.testing import CliRunner
from moto import mock_cloudformation, mock_ec2

from remote_docker_aws.cli_commands import cli
from remote_docker_aws.config import RemoteDockerConfigProfile


AWS_REGION = "ca-central-1"


patch_exec = mock.patch("os.execvp", autospec=True)
patch_run = mock.patch("subprocess.run", autospec=True)


def test_cli_entrypoint_runs_successfully():
    output = subprocess.check_output("remote-docker-aws --help", shell=True)
    assert output

    output = subprocess.check_output("rd --help", shell=True)
    assert output


class MockProfile(RemoteDockerConfigProfile):
    @property
    def aws_region(self) -> str:
        return AWS_REGION


@mock_cloudformation
@mock_ec2
class TestCLICommandsWithMoto:
    @pytest.fixture(autouse=True)
    def with_empty_config(self):
        with mock.patch(
            "remote_docker_aws.cli_commands.RemoteDockerConfigProfile.from_json_file",
            autospec=True,
        ) as mock_from_json_file:
            mock_from_json_file.return_value = MockProfile({})
            yield

    @pytest.fixture
    def cli_runner(self):
        runner = CliRunner(mix_stderr=False)
        with runner.isolated_filesystem():
            yield runner

    @pytest.fixture
    def create_instance(self, cli_runner):
        def create():
            with mock.patch(
                "remote_docker_aws.providers.wait_until_port_is_open", autospec=True
            ):
                if not isinstance(os.execvp, mock.MagicMock):
                    with mock.patch("os.execvp"):
                        result = cli_runner.invoke(cli, ["create"])
                else:
                    result = cli_runner.invoke(cli, ["create"])
                return result

        return create

    @pytest.fixture
    def delete_instance(self, cli_runner):
        def delete():
            result = cli_runner.invoke(cli, ["delete"], input="y")
            return result

        return delete

    @pytest.fixture
    def instance(self, create_instance, delete_instance):
        @contextmanager
        def _instance():
            create_instance()
            try:
                yield
            finally:
                delete_instance()

        return _instance

    def test_create_and_delete(self, create_instance, delete_instance):
        result = create_instance()
        assert result.exit_code == 0

        result = delete_instance()
        assert result.exit_code == 0

    @patch_exec
    def test_ssh(self, mock_exec, cli_runner, instance):
        with instance():
            result = cli_runner.invoke(cli, ["ssh"])
        assert result.exit_code == 0
        mock_exec.assert_called_once()

    def test_start(self, cli_runner, instance):
        with instance():
            result = cli_runner.invoke(cli, ["start"])
        assert result.exit_code == 0

    def test_stop(self, cli_runner, instance):
        with instance():
            result = cli_runner.invoke(cli, ["stop"])
        assert result.exit_code == 0

    def test_ip(self, cli_runner, instance):
        with instance():
            result = cli_runner.invoke(cli, ["ip"])
        assert result.exit_code == 0
        assert result.stdout

    @mock.patch(
        "remote_docker_aws.core.RemoteDockerClient.create_keypair", autospec=True
    )
    def test_create_keypair(self, mock_create_keypair, cli_runner, instance):
        with instance():
            result = cli_runner.invoke(cli, ["create-keypair"])
        assert result.exit_code == 0
        assert mock_create_keypair.call_count == 1

    @pytest.mark.parametrize("local,remote", [(None, None), ("80:80", "3300:3300")])
    @patch_run
    def test_tunnel(self, mock_run, local, remote, cli_runner, instance):
        args = ["tunnel"]

        if local:
            args.extend(["--local", local])
        if remote:
            args.extend(["--remote", remote])

        with instance():
            result = cli_runner.invoke(cli, args)
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @pytest.mark.parametrize("directories", [(["/data/mock_dir1", "/data/mock_dir2"])])
    @patch_exec
    @patch_run
    def test_sync(self, mock_run, mock_exec, directories, cli_runner, instance):
        args = ["sync"]

        if directories:
            args.extend(directories)

        with instance():
            result = cli_runner.invoke(cli, args)
        assert result.exit_code == 0
        assert mock_run.call_count == 2
        mock_exec.assert_called_once()

    @mock.patch(
        "remote_docker_aws.core.RemoteDockerClient.enable_termination_protection",
        autospec=True,
    )
    def test_enable_termination_protection(
        self, mock_enable_termination_protection, cli_runner, instance
    ):
        with instance():
            result = cli_runner.invoke(cli, ["enable-termination-protection"])
        assert result.exit_code == 0
        mock_enable_termination_protection.assert_called_once()

    @mock.patch(
        "remote_docker_aws.core.RemoteDockerClient.disable_termination_protection",
        autospec=True,
    )
    def test_disable_termination_protection(
        self, mock_disable_termination_protection, cli_runner, instance
    ):
        with instance():
            result = cli_runner.invoke(cli, ["disable-termination-protection"])
        assert result.exit_code == 0
        mock_disable_termination_protection.assert_called_once()

    def test_delete_raises_error_if_termination_protection_is_enabled(
        self, cli_runner, instance
    ):
        with instance():
            result = cli_runner.invoke(cli, ["enable-termination-protection"])
            assert result.exit_code == 0
            result = cli_runner.invoke(cli, ["delete"])
            assert result.exit_code == 1
            assert result.stderr is not None

            result = cli_runner.invoke(cli, ["disable-termination-protection"])
            assert result.exit_code == 0
            result = cli_runner.invoke(cli, ["delete"], input="y")
            assert result.exit_code == 0
