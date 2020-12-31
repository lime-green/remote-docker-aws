import json
import os
import pytest
from contextlib import contextmanager
from unittest import mock

from remote_docker_aws.config import RemoteDockerConfigProfile


@pytest.fixture
def mock_contents():
    return dict(aws_profile="mock_aws_profile", key_path="~/mock_key_file")


@pytest.fixture
def file_open_mocker():
    @contextmanager
    def _mocker(mock_return_value, is_json=True):
        if is_json:
            mock_return_value = json.dumps(mock_return_value)

        with mock.patch("builtins.open") as mock_open:
            mock_open.side_effect = mock.mock_open(read_data=mock_return_value)
            yield mock_open

    return _mocker


@mock.patch("os.path.isfile", return_value=False)
def test_handles_file_does_not_exist(_mock_is_file):
    config = RemoteDockerConfigProfile.from_json_file("file_does_not_exist")
    assert config.config_dict == {}


@mock.patch("os.path.isfile", return_value=True)
def test_handles_file_does_exist(_mock_is_file, file_open_mocker, mock_contents):
    with file_open_mocker(mock_contents):
        config = RemoteDockerConfigProfile.from_json_file("file_does_exist")
    assert config.config_dict == mock_contents


def test_settings_with_defaults():
    config = RemoteDockerConfigProfile({})
    assert config.instance_type == "t3.medium"
    assert config.key_path == os.path.expanduser("~/.ssh/id_rsa_remote_docker")
    assert config.local_port_forwards == {}
    assert config.remote_port_forwards == {}
    assert config.sync_ignore_patterns_git == []
    assert config.user_id is None
    assert config.key_pair_name == "remote-docker-keypair"
    assert config.instance_service_name == "remote-docker-ec2-agent"
    assert config.project_code == "remote-docker"
    assert config.watched_directories == []
    assert config.volume_size == 30


@mock.patch(
    "remote_docker_aws.config.RemoteDockerConfigProfile._boto3_session",
    new_callable=mock.PropertyMock,
)
def test_aws_region_uses_boto_session_fallback(mock_session):
    mock_session.return_value = mock.MagicMock(region_name="session_aws_region")

    config = RemoteDockerConfigProfile({})
    assert config.aws_region == "session_aws_region"

    config = RemoteDockerConfigProfile(dict(aws_region="override_aws_region"))
    assert config.aws_region == "override_aws_region"


def test_settings_with_profile():
    config_dict = {
        "aws_region": "ca-central-1",
        "key_path": "~/mock_key_path",
        "local_port_forwards": {"base": {"443": "443", "80": "80"}},
        "sync_ignore_patterns_git": ["test.py"],
        "user_id": "jon_smith",
        "volume_size": 40,
        "default_profile": "test_profile",
        "profiles": {
            "test_profile": {
                "aws_region": "us-east-1",
                "sync_ignore_patterns_git": ["test2.py"],
                "local_port_forwards": {"db": {"3306": "3306"}},
                "remote_port_forwards": {"local-webpack-app": {"8080": "8080"}},
            }
        },
    }
    config = RemoteDockerConfigProfile(config_dict)
    assert config.aws_region == "us-east-1"
    assert config.key_path == os.path.expanduser(config_dict["key_path"])
    assert config.local_port_forwards == {
        "base": {"443": "443", "80": "80"},
        "db": {"3306": "3306"},
    }
    assert config.sync_ignore_patterns_git == ["test.py", "test2.py"]
    assert config.remote_port_forwards == {"local-webpack-app": {"8080": "8080"}}
    assert config.user_id == "jon_smith"

    user_id = "jon_smith"
    assert config.key_pair_name == f"remote-docker-keypair-{user_id}"
    assert config.instance_service_name == f"remote-docker-ec2-agent-{user_id}"
    assert config.project_code == f"remote-docker-{user_id}"
    assert config.volume_size == 40
