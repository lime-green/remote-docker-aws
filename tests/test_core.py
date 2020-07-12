import ipaddress
from cryptography.hazmat.primitives import serialization as crypto_serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend as crypto_default_backend
from pkg_resources import EntryPoint
from unittest import mock

import pytest
from moto import mock_cloudformation, mock_ec2

from remote_docker_aws.config import RemoteDockerConfigProfile
from remote_docker_aws.core import (
    create_remote_docker_client,
    get_ec2_client,
)


KEY_PATH = "/fake_key_path"
REGION = "ca-central-1"


patch_exec = mock.patch("os.execvp", autospec=True)
patch_run = mock.patch("subprocess.run", autospec=True)
patch_get_ip = mock.patch(
    "remote_docker_aws.core.RemoteDockerClient.get_ip", autospec=True
)


def generate_ssh_public_key():
    key = rsa.generate_private_key(
        backend=crypto_default_backend(), public_exponent=65537, key_size=2048
    )
    return (
        key.public_key()
        .public_bytes(
            crypto_serialization.Encoding.OpenSSH,
            crypto_serialization.PublicFormat.OpenSSH,
        )
        .decode()
    )


def is_valid_ip(address):
    try:
        ipaddress.ip_address(address)
        return True
    except ValueError:
        return False


@pytest.fixture(autouse=True, scope="module")
def fix_dependency_conflict():
    """
    To resolve the following:

    ```
    ERROR: cfn-lint 0.33.2 has requirement networkx~=2.4; python_version >= "3.5",
    but you'll have networkx 2.1 which is incompatible.
    ```

    can't fix because sceptre is pinned at networkx==2.1 right now :(
    """
    with mock.patch.object(EntryPoint, "require", return_value=True):
        yield


@mock_cloudformation
@mock_ec2
class TestCore:
    @pytest.fixture
    def remote_docker_client(self):
        config = RemoteDockerConfigProfile(
            config_dict=dict(
                project_code="mock_project",
                aws_region=REGION,
                instance_service_name="mock_instance",
                instance_type="c4.xlarge",
                local_port_forwards=dict(test_local={"80": "80"}),
                remote_port_forwards=dict(test_remote={"8080": "8080"}),
                key_path=KEY_PATH,
                watched_directories=["/fake/dir"],
                sync_ignore_patterns_git=["test.py"],
            )
        )
        return create_remote_docker_client(config)

    def test_get_ip_when_no_instances_running(self, remote_docker_client):
        with pytest.raises(RuntimeError) as exc:
            remote_docker_client.get_ip()
            assert (
                str(exc.value)
                == "There are no valid reservations, did you create the instance?"
            )

    @patch_exec
    @mock.patch("remote_docker_aws.core.wait_until_port_is_open", autospec=True)
    def test_creates_and_interacts_with_instance(
        self, mock_wait, mock_execvp, remote_docker_client
    ):
        remote_docker_client.create_instance()
        mock_wait.assert_called_once()
        mock_execvp.assert_called_once()

        assert is_valid_ip(remote_docker_client.get_ip())
        assert remote_docker_client.get_instance_state() == "running"

        remote_docker_client.stop_instance()
        assert remote_docker_client.get_instance_state() == "stopped"

        remote_docker_client.start_instance()
        assert remote_docker_client.get_instance_state() == "running"

        remote_docker_client.delete_instance()
        with pytest.raises(RuntimeError):
            remote_docker_client.get_ip()

    @patch_get_ip
    @patch_exec
    @patch_run
    def test_sync(self, mock_run, mock_execvp, mock_get_ip, remote_docker_client):
        mock_get_ip.return_value = "1.2.3.4"
        remote_docker_client.sync()

        assert mock_run.call_count == 2
        call_1, call_2 = mock_run.call_args_list
        assert call_1[0][0] == [
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            "-i",
            "/fake_key_path",
            "ubuntu@1.2.3.4",
            "sudo",
            "install",
            "-d",
            "-o",
            "ubuntu",
            "-g",
            "ubuntu",
            "-p",
            "/fake/dir",
        ]
        expected_unison_cmd = [
            "unison-gitignore",
            "/fake",
            "ssh://ubuntu@1.2.3.4//fake",
            "-prefer",
            "/fake",
            "-batch",
            "-sshargs",
            "-i /fake_key_path",
            "-ignore=Regex ^(.+/)?test\\.py(/.*)?$",
            "-path",
            "dir",
            "-force",
            "/fake",
        ]
        assert call_2[0][0] == expected_unison_cmd

        mock_execvp.assert_called_once()
        assert mock_execvp.call_args[0][0] == expected_unison_cmd[0]
        assert mock_execvp.call_args[0][1] == [
            *expected_unison_cmd[:-2],
            "-repeat",
            "watch",
        ]

    @patch_get_ip
    @patch_run
    def test_tunnel(self, mock_run, mock_get_ip, remote_docker_client):
        mock_get_ip.return_value = "1.2.3.4"
        remote_docker_client.start_tunnel()

        mock_run.assert_called_once()
        assert mock_run.call_args[0][0] == [
            "sudo",
            "ssh",
            "-v",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=60",
            "-N",
            "-T",
            "-i",
            "/fake_key_path",
            "ubuntu@1.2.3.4",
            "-L",
            "localhost:23755:localhost:2375",
            "-L",
            "localhost:80:localhost:80",
            "-R",
            "0.0.0.0:8080:localhost:8080",
        ]

    @patch_run
    def test_create_keypair(self, mock_run, remote_docker_client):
        with mock.patch("builtins.open") as mock_open:
            mock_open.side_effect = mock.mock_open(read_data=generate_ssh_public_key())
            remote_docker_client.create_keypair()

        assert mock_run.call_count == 2
        call_1, call_2 = mock_run.call_args_list
        assert call_1[0][0] == [
            "ssh-keygen",
            "-t",
            "rsa",
            "-b",
            "4096",
            "-f",
            "/fake_key_path",
        ]
        assert call_2[0][0] == ["ssh-add", "-K", "/fake_key_path"]

        key_pairs = get_ec2_client(REGION).describe_key_pairs()["KeyPairs"]
        assert len(key_pairs) == 1
        key_pair = key_pairs[0]
        assert key_pair["KeyName"] == "remote-docker-keypair"
