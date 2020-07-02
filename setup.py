import os
from os.path import join, exists
from setuptools import find_packages, setup

base_dir = os.path.dirname(__file__)
readme_path = join(base_dir, "README.md")
if exists(readme_path):
    with open(readme_path) as stream:
        long_description = stream.read()
else:
    long_description = ""

INSTALL_REQUIRES = ("boto3", "sceptre>=2.3", "click", "unison-gitignore")


setup(
    name="remote-docker-aws",
    install_requires=INSTALL_REQUIRES,
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    description="Client to control a remote-docker agent",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Josh DM",
    url="https://github.com/lime-green/remote-docker-aws",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    package_data={
        # Is this 2020?
        "remote_docker_aws": ["*", "*/*", "*/*/*", "*/*/*/*"]
    },
    entry_points={
        "console_scripts": [
            "remote-docker-aws = remote_docker_aws.main:main",
            "rd = remote_docker_aws.main:main",
        ]
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Libraries",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    license="MIT",
    keywords=["docker", "aws", "development", "macos", "linux"],
)
