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
    assert config.instance_type == "t2.medium"
    assert config.key_path == os.path.expanduser("~/.ssh/id_rsa_remote_docker")
    assert config.local_port_forwards == {}
    assert config.remote_port_forwards == {}
    assert config.sync_ignore_patterns_git == []


def test_settings_with_no_defaults():
    config = RemoteDockerConfigProfile({})

    with pytest.raises(KeyError):
        config.aws_profile

    with pytest.raises(KeyError):
        config.aws_region

    with pytest.raises(KeyError):
        config.watched_directories


@mock.patch.dict(
    os.environ, {"AWS_PROFILE": "mock_aws_profile", "AWS_REGION": "mock_aws_region"}
)
def test_settings_with_env_var_fallback():
    config = RemoteDockerConfigProfile({})
    assert config.aws_profile == "mock_aws_profile"
    assert config.aws_region == "mock_aws_region"


def test_settings_with_profile():
    config_dict = {
        "aws_region": "ca-central-1",
        "key_path": "~/mock_key_path",
        "local_port_forwards": {"base": {"443": "443", "80": "80"}},
        "sync_ignore_patterns_git": ["test.py"],
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


def test_settings_that_can_be_extended():
    config_dict = {
        "local_port_forwards": {"db": {3306: 3306}},
        "watched_directories": ["/projects/blog"],
    }
    config = RemoteDockerConfigProfile(config_dict)

    assert config.watched_directories == config_dict["watched_directories"]
    config.add_watched_directories(["/projects/blog2"])
    assert config.watched_directories == ["/projects/blog", "/projects/blog2"]

    assert config.local_port_forwards == config_dict["local_port_forwards"]
    config.add_local_port_forwards("test", {3000: 3000})
    assert config.local_port_forwards == {"db": {3306: 3306}, "test": {3000: 3000}}

    assert config.remote_port_forwards == {}
    config.add_remote_port_forwards("test", {8080: 8080})
    assert config.remote_port_forwards == {"test": {8080: 8080}}
