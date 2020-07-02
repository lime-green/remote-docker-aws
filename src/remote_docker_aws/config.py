import json
import os
from typing import Dict, List

from .constants import INSTANCE_TYPE_DEFAULT, PORT_MAP_TYPE


_UNSET = object()


class JSONConfig:
    IGNORE_FIELDS = []

    def __init__(self, config_dict, *args, **kwargs):
        self.config_dict = config_dict

    @classmethod
    def from_json_file(cls, config_json_path, *args, **kwargs):
        config_json_path = os.path.expanduser(config_json_path)

        if os.path.isfile(config_json_path):
            with open(config_json_path, "r") as fh:
                config_dict = json.load(fh)
        else:
            config_dict = {}
        return cls(config_dict, *args, **kwargs)

    @classmethod
    def _fetch_or_raise_error(cls, data, key):
        try:
            return data[key]
        except KeyError:
            raise KeyError(f"{key} not found in {data} and is required")

    @classmethod
    def _override_data(cls, default_data, override_data):
        data = {}

        # Set default config values from outermost scope
        for k, v in default_data.items():
            if k in cls.IGNORE_FIELDS:
                continue
            data[k] = v

        if override_data:
            for k, v in override_data.items():
                default_value = data.get(k)

                if isinstance(default_value, list):
                    # List config values will be extended from default
                    data[k].extend(v)
                elif isinstance(default_value, dict):
                    # Dict config values will be merged
                    # Note: it's not a deep merge, and I don't think it should be
                    data[k].update(v)
                else:
                    # Otherwise, just replace with the profile values
                    data[k] = v
        return data

    def get_attribute(self, key, default=_UNSET):
        try:
            return self._fetch_or_raise_error(self.config_dict, key)
        except KeyError:
            if default is _UNSET:
                raise
            return default

    def __str__(self):
        return str(self.config_dict)


class JSONConfigWithProfile(JSONConfig):
    IGNORE_FIELDS = ["profiles", "default_profile"]

    def __init__(self, config_dict, profile_name=None):
        config_dict = self.normalize_data(config_dict, profile_name)

        super().__init__(config_dict=config_dict)

    @classmethod
    def normalize_data(cls, raw_config, profile_name):
        profile_data = None

        if profile_name is None and "default_profile" in raw_config:
            profile_name = raw_config["default_profile"]
        if profile_name:
            profiles = cls._fetch_or_raise_error(raw_config, "profiles")
            profile_data = cls._fetch_or_raise_error(profiles, profile_name)

        return cls._override_data(raw_config, profile_data)


class RemoteDockerConfigProfile(JSONConfigWithProfile):
    @property
    def aws_profile(self) -> str:
        if "AWS_PROFILE" in os.environ:
            return self.get_attribute("aws_profile", os.environ["AWS_PROFILE"])
        return self.get_attribute("aws_profile")

    @property
    def aws_region(self) -> str:
        if "AWS_REGION" in os.environ:
            return self.get_attribute("aws_region", os.environ["AWS_REGION"])
        return self.get_attribute("aws_region")

    @property
    def key_path(self) -> str:
        return os.path.expanduser(
            self.get_attribute("key_path", "~/.ssh/id_rsa_remote_docker")
        )

    @property
    def sync_ignore_patterns_git(self) -> List[str]:
        return self.get_attribute("sync_ignore_patterns_git", [])

    @property
    def remote_port_forwards(self) -> PORT_MAP_TYPE:
        return self.get_attribute("remote_port_forwards", {})

    @property
    def local_port_forwards(self) -> PORT_MAP_TYPE:
        return self.get_attribute("local_port_forwards", {})

    @property
    def watched_directories(self) -> List[str]:
        return [
            os.path.expanduser(watched_dir)
            for watched_dir in self.get_attribute("watched_directories")
        ]

    @property
    def instance_type(self) -> str:
        return self.get_attribute("instance_type", INSTANCE_TYPE_DEFAULT)

    def add_watched_directories(self, dirs: List[str]):
        self.config_dict.setdefault("watched_directories", [])
        self.config_dict["watched_directories"].extend(dirs)

    def add_local_port_forwards(self, key: str, local_port_forwards: Dict):
        self.config_dict.setdefault("local_port_forwards", {})
        self.config_dict["local_port_forwards"][key] = local_port_forwards

    def add_remote_port_forwards(self, key: str, remote_port_forwards: Dict):
        self.config_dict.setdefault("remote_port_forwards", {})
        self.config_dict["remote_port_forwards"][key] = remote_port_forwards
