import pytest
from pathlib import Path

from remote_docker_aws.util import get_replica_and_sync_paths_for_unison


class TestReplicaAndSyncPathsForUnison:
    def test_it_finds_replica_and_sync_paths(self):
        replica_path, sync_paths = get_replica_and_sync_paths_for_unison(
            ["/projects/blog", "/projects/analytics"]
        )
        assert replica_path == Path("/projects")
        assert sync_paths == [Path("blog"), Path("analytics")]

    def test_it_raises_error_when_no_dirs(self):
        with pytest.raises(ValueError):
            get_replica_and_sync_paths_for_unison([])

    def test_it_raises_error_for_two_roots(self):
        with pytest.raises(ValueError):
            get_replica_and_sync_paths_for_unison(["/", "/"])

    def test_it_raises_error_when_no_common_non_root_directory(self):
        with pytest.raises(ValueError):
            get_replica_and_sync_paths_for_unison(["/tmp", "/data"])
