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
