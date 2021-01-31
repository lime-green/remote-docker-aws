## Remote Docker on AWS for local development
[![PyPI version](https://badge.fury.io/py/remote-docker-aws.svg)](https://badge.fury.io/py/remote-docker-aws)
![Python versions](https://img.shields.io/pypi/pyversions/remote-docker-aws.svg?style=flat-square&label=Python%20Versions)

Use docker to develop services, but without the overhead of running docker on your machine! This is a development tool that you should use if your machine is low performance, or if you are running many docker services.

### Why is this useful?

Frees up your local machine for useful tasks
such as running your code editor, browser, and email, leaving running Docker to a dedicated server instance.
The result is that your local machine functions faster, uses up less disk space, and consumes less power.
MacOS users will also see noticeable speed improvements since Docker on Linux (which is
what the remote hosts runs) is much more performant.

The downsides:
- SSH tunnel communication is slower than local communication. However using an AWS region with low ping makes the latency unnoticeable. Find the region fastest for you using [this site](https://www.cloudping.info/)
- Some more setup required to get everything configured properly and running (tunneling ports, syncing file changes)
- Running the ec2 instance incurs an additional cost over running locally, although a t3.medium instance in Canada only costs just under 5 cents/hour

How it works: two processes are run, a sync and a tunnel process. 
- The sync process keeps local and remote files in sync so that the docker process run remotely can use docker volumes transparently
- The tunnel process forwards ports needed so your local system can communicate with docker, plus additional ports as required, such as port 443 for browser communication

## Setup
1. First login to your AWS account and [create access keys to access AWS through the CLI](https://docs.aws.amazon.com/powershell/latest/userguide/pstools-appendix-sign-up.html)

    You will need the following IAM policies:
    - AmazonEC2FullAccess
    - AWSCloudFormationFullAccess

    And now in your terminal:

    ```bash
    # Replace josh with your name
    # You will need to setup an AWS account if you don't have one
    # and create access key credentials

    aws configure --profile josh
    export AWS_PROFILE=josh
    ```

1. Install pre-requisites

   Have [Homebrew](https://brew.sh/) (Available on both macOS and Linux now!)

   Have [pipx](https://github.com/pipxproject/pipx)

    ```bash
   pipx install remote-docker-aws
   pipx install unison-gitignore

   # Install unison sync utility
   brew install unison

   # Install file-watcher driver for unison
   # On MacOS:
   brew install autozimu/homebrew-formulas/unison-fsmonitor

   # Or, on Linux since the above formula doesn't work:
   brew install eugenmayer/dockersync/unox
    ```

1. Generate and upload a keypair to AWS

    ```bash
   # Note: bash users can use `rd` instead of `remote-docker-aws`. zsh users cannot since zsh aliases `rd` to `rmdir` (!)
   remote-docker-aws create-keypair
    ```

1. Create the ec2 instance

    ```bash
   remote-docker-aws create
    ```

## Daily Running

Note: QUIT Docker Desktop (or any local docker-agent equivalent) when using the remote agent

1. Start the remote-docker ec2 instance
    ```bash
    remote-docker-aws start
    ```

1. In one terminal start the tunnel so that the ports you need to connect to are exposed
    ```bash
    remote-docker-aws tunnel

   # Usually it's preferable just to forward the ports to same port
   # so eg. with mysql on docker exposing port 3306 and nginx on docker exposing port 80:
   remote-docker-aws tunnel -l 80:80 -l 3306:3306

   # You can forward remote ports as needed with the "-r" option:
   # which can be used so the docker instance can access services running locally (eg. webpack)
   remote-docker-aws tunnel -r 8080:8080
    ```

1. In another terminal sync file changes to the remote instance:
    ```bash
    # Add any more paths you need to sync here, or add them to the config file
    # You will need to sync directories that are mounted as volumes by docker
    remote-docker-aws sync ~/blog

    # If watched directories are supplied in ~/.remote-docker.config.json
    # then simply call:
    remote-docker-aws sync
    ```

1. Make sure to set `DOCKER_HOST`:
    ```bash
    # In the terminal you use docker, or add to ~/.bashrc so it applies automatically
    export DOCKER_HOST="tcp://localhost:23755"
    ```

   Now you can use docker as you would normally:
   - `docker build -t myapp .`
   - `docker-compose up`
   - etc.

   You can usually skip starting your services again since when the instance
   boots, it will start up docker and resume where it left off from the day before.

1. Develop and code! All services should be accessible and usable as usual
as long as you are running `remote-docker-aws tunnel` and are forwarding the ports you need

1. When you're done for the day don't forget to stop the instance to save money:
    ```bash
    remote-docker-aws stop
    ```

## Config File
Looks for a config file at the path `~/.remote-docker.config.json` by default,
which can be overriden by passing `--config-path`. The config file is not necessary
and CLI usage is possible without it as long as AWS_PROFILE and AWS_REGION environment variables are set

An example `.remote-docker.config.json` file:
```json
{
    "key_path": "~/.ssh/id_rsa_remote_docker",
    "sync_ignore_patterns_git": [
        "**/*.idea/",
        "**/*.git/",
        "**/*~",
        "**/*.sw[pon]"
    ],
    "profiles": {
        "blog": {
            "sync_ignore_patterns_git": [
                "**/notes/"
            ],
            "remote_port_forwards": {
                "local-webpack-app": {"8080": "8080"}
            },
            "local_port_forwards": {
                "blog_app": {"443": "443", "80":  "8000"},
                "blog_db": {"3306": "3306"}
            },
            "watched_directories": [
                "~/.aws",
                "~/blog"
            ]
        }
    },
    "default_profile": "blog"
}
```

```bash
Usage: remote-docker-aws [OPTIONS] COMMAND [ARGS]...

Options:
  --profile TEXT      Name of the remote-docker-aws profile to use
  --config-path TEXT  Path of the remote-docker-aws JSON config
```

The current configurable values are:
#### `aws_region` (takes precedence over `AWS_REGION` and `.aws/config`)
- The region to create the instance in

#### `instance_type`
- Type of ec2 instance, defaults to: `t3.medium`

#### `key_path`
  - defaults to: `~/.ssh/id_rsa_remote_docker`

#### `local_port_forwards`
  - defaults to: `{}`
  - Object containing label -> port mapping objects for opening the ports on the remote host.
    A mapping of `"remote_port_forwards": {"my_app": {"80": "8080"}}` will open port 80 on your local machine
    and point it to port 8080 of the remote-docker instance (which ostensibly a container is listening on).
    The name doesn't do anything except help legibility.

#### `remote_port_forwwards`
  - defaults to: `{}`
  - Similar to `local_port_forwards` except will open the port on the remote instance.

    This is useful to have frontend webpack apps accessible on the remote host

#### `sync_ignore_patterns_git`
  - defaults to: `[]`
  - use `.gitignore` syntax, and make sure to use the directory wildcard as needed

#### `user_id`
  - defaults to `None`
  - Used to uniquely identify the instance, this is useful if multiple remote-docker agents
  will be created in the same AWS account

#### `watched_directories`
 - defaults to: `[]`
 - list of paths to watch by `remote-docker-aws sync`

#### `volume_size`
 - defaults to: `30` (GB)
 - Size of the ec2 volume.

---

Profiles are a way to organize and override settings for different projects.
Values nested in a profile override the values defined outside a profile,
except for lists and dictionaries which are merged with the values outside the profile


## Cost
A t3.medium instance on ca-central-1 currently costs $0.046 /hour. [See current prices](https://aws.amazon.com/ec2/pricing/on-demand/)

Nothing else used should incur any cost with reasonable usage

## Notes
- See `remote-docker-aws --help` for more information on the commands available

