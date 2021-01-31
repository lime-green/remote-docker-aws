import logging
import os
import pathlib
import socket
import time
from typing import List

import colorlog

log_level = os.environ.get("REMOTE_DOCKER_LOG_LEVEL", "INFO")
logger = logging.getLogger("remote-docker")
logger.setLevel(getattr(logging, log_level))
logFormatter = colorlog.ColoredFormatter(
    fmt="%(log_color)s%(name)s :: %(levelname)-8s :: %(message)s"
)
handler = logging.StreamHandler()
handler.setFormatter(logFormatter)
logger.addHandler(handler)


def get_replica_and_sync_paths_for_unison(dirs: List[str]):
    """
    Converts directory paths into replica + sync paths for unison to understand

    The one caveat here is that we want to only call unison once with multiple paths
    and the replica path has to be common to all of them. A "/" replica path is not
    accepted by unison for some reason so we will just take the second path after
    that, and make sure that it's common between all the dirs
    """
    if not dirs:
        raise ValueError("Directories must not be empty")

    replica_path = None
    sync_paths = []

    for dir_path in dirs:
        dir_parts = pathlib.Path(dir_path).parts
        if len(dir_parts) < 2:
            raise ValueError("Directories must be children of the root directory")

        path_first_dir = pathlib.Path(*dir_parts[0:2])

        if replica_path is None:
            replica_path = path_first_dir
        elif path_first_dir != replica_path:
            raise ValueError("Directories must share a common path other than '/'")
        sync_paths.append(pathlib.Path(*dir_parts[2:]))

    return replica_path, sync_paths


def is_port_open(ip, port, timeout=2):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    result = sock.connect_ex((ip, port))
    return result == 0


def wait_until_port_is_open(ip, port, sleep_time=3, max_attempts=10):
    attempts = 0
    while not is_port_open(ip, port):
        attempts += 1
        if attempts >= max_attempts:
            raise RuntimeError(f"{ip}:{port} has not opened")
        time.sleep(sleep_time)
