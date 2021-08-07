import os
from unittest import mock

import pytest


@pytest.fixture(autouse=True, scope="function")
def ensure_aws_is_mocked():
    if os.environ.get("AWS_PROFILE"):
        del os.environ["AWS_PROFILE"]
    if os.environ.get("AWS_REGION"):
        del os.environ["AWS_REGION"]

    with mock.patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "testing",
            "AWS_SECRET_ACCESS_KEY": "testing",
            "AWS_SECURITY_TOKEN": "testing",
            "AWS_SESSION_TOKEN": "testing",
        },
    ):
        yield


@pytest.fixture(autouse=True, scope="function")
def ensure_sleep_is_mocked():
    with mock.patch("time.sleep"):
        yield


@pytest.fixture(autouse=True)
def mock_exec():
    with mock.patch("os.execvp", autospec=True) as mock_exec_:
        yield mock_exec_


@pytest.fixture(autouse=True)
def mock_run():
    with mock.patch("subprocess.run", autospec=True) as mock_run_:
        yield mock_run_


@pytest.fixture
def mock_user():
    return "test_user"


@pytest.fixture(autouse=True)
def mock_getuser(mock_user):
    with mock.patch("remote_docker_aws.core.getuser", return_value=mock_user):
        yield
