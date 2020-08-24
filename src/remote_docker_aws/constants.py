import os
import pathlib
from typing import Dict


DOCKER_PORT_FORWARD = {"23755": "2375"}

KEY_PAIR_NAME = "remote-docker-keypair"
INSTANCE_USERNAME = "ubuntu"
# Used to identify the ec2 instance
INSTANCE_SERVICE_NAME = "remote-docker-ec2-agent"
INSTANCE_TYPE_DEFAULT = "t3.medium"
SCEPTRE_PATH = os.path.join(pathlib.Path(__file__).parent.absolute(), "sceptre")
SCEPTRE_PROJECT_CODE = "remote-docker"
# AWS free tier includes 30GB, so seems like a sensible default
VOLUME_SIZE_DEFAULT = 30


# Looked up via https://cloud-images.ubuntu.com/locator/ec2/
# With filters:
# Version: 18.04 LTS
# Instance Type: hvm:ebs-ssd
# Release: 20200626
AWS_REGION_TO_UBUNTU_AMI_MAPPING = {
    "us-west-2": "ami-053bc2e89490c5ab7",
    "us-west-1": "ami-0d705db840ec5f0c5",
    "us-east-2": "ami-0a63f96e85105c6d3",
    "us-east-1": "ami-0ac80df6eff0e70b5",
    "sa-east-1": "ami-0faf2c48fc9c8f966",
    "me-south-1": "ami-0ca656ad4cf917e1f",
    "eu-west-3": "ami-0e11cbb34015ff725",
    "eu-west-2": "ami-00f6a0c18edb19300",
    "eu-west-1": "ami-089cc16f7f08c4457",
    "eu-south-1": "ami-08bb6fa4a2d8676d4",
    "eu-north-1": "ami-0f920d75f0ce2c4bb",
    "eu-central-1": "ami-0d359437d1756caa8",
    "ca-central-1": "ami-065ba2b6b298ed80f",
    "ap-southeast-2": "ami-0bc49f9283d686bab",
    "ap-southeast-1": "ami-063e3af9d2cc7fe94",
    "ap-south-1": "ami-02d55cb47e83a99a0",
    "ap-northeast-3": "ami-056ee91a6ed694f5d",
    "ap-northeast-2": "ami-0d777f54156eae7d9",
    "ap-northeast-1": "ami-0cfa3caed4b487e77",
    "ap-east-1": "ami-c42464b5",
    "af-south-1": "ami-079652134906bcbad",
}

PORT_MAP_TYPE = Dict[str, Dict[str, str]]
