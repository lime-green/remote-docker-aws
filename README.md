## Remote Docker on AWS for local development
[![PyPI version](https://badge.fury.io/py/remote-docker-aws.svg)](https://badge.fury.io/py/remote-docker-aws)

Why is this useful?

So that your local machine can be dedicated to useful tasks
such as running your code editor, browser, email, etc. leaving the docker-running
to machines dedicated for this, and so your local machine functions better and faster.
Docker also runs much more efficiently on Linux
than macOS, so this is particularly useful for mac users

Downsides:
- SSH tunnel communication vs. local communication: use an aws-region with lowest ping for you using [this site](https://ping.psa.fun/) or [this site](https://www.cloudping.info/)
- Some more setup required (tunneling, file watcher, config)
- Cost, although it only costs me  around 5 cents / hour

## Setup
1. First setup your aws-cli to connect to your AWS profile,
and [create access keys to access AWS through the CLI](https://docs.aws.amazon.com/powershell/latest/userguide/pstools-appendix-sign-up.html)

    You will need the following IAM policies:
    - AmazonEC2FullAccess
    - AWSCloudFormationFullAccess

    ```bash
    # Replace josh with your name
    # You will need to setup an AWS account if you don't have one
    # and create access key credentials

    aws configure --profile josh
    export AWS_PROFILE=josh
    ```

1. Install pre-requisites

   Have [pipx](https://github.com/pipxproject/pipx)

   Have [Homebrew](https://brew.sh/) (Available on both macOS and Linux now!)

    ```bash
   pipx install remote-docker-aws

   # Install filewatcher utilities
   brew install unison

   # On MacOS:
   brew install autozimu/homebrew-formulas/unison-fsmonitor

   # Or, on Linux since the above formula doesn't work:
   brew install eugenmayer/dockersync/unox
    ```

1. Generate and upload a keypair to AWS

    ```bash
   rd create-keypair
    ```

1. Create the ec2 instance

    ```bash
   rd create
    ```

## Daily Running

Note: QUIT Docker Desktop (or any local docker-agent equivalent) when using the remote agent

1. Start the remote-docker ec2 instance
    ```bash
    rd start
    ```

1. In one terminal start the tunnel so that the ports you need to connect to are exposed
    ```bash
    rd tunnel

   # Usually it's preferable just to forward the ports to same port
   # so eg. with mysql on docker exposing port 3306 and nginx on docker exposing port 80:
   rd tunnel -l 80:80 -l 3306:3306

   # You can forward remote ports as needed with the "-r" option:
   # which can be used so the docker instance can access services running locally (eg. webpack)
   rd tunnel -r 8080:8080
    ```

1. In another terminal sync file changes to the remote instance:
    ```bash
    # Add any more paths you need to sync here, or add them to the config file
    # You will need to sync directories that are mounted as volumes by docker
    rd sync ~/blog
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
as long as you are running `rd tunnel` and are forwarding the ports you need

1. When you're done for the day don't forget to stop the instance to save $:
    ```bash
    rd stop
    ```

## Config File
Looks for a config file at the path `~/.remote-docker.config.json` by default,
which can be overriden by passing `--config-path`. The config file is not necessary
and CLI usage is possible without it as long as AWS_PROFILE and AWS_REGION environment variables are set

An example `.remote-docker.config.json` file:
```json
{
    "aws_profile": "josh",
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
Usage: rd [OPTIONS] COMMAND [ARGS]...

Options:
  --profile TEXT      Name of the remote-docker profile to use
  --config-path TEXT  Path of the remote-docker JSON config
```

The current configurable values are:
#### `aws_profile` (takes precedence over `AWS_PROFILE`)
- Needed in order to authenticate with AWS

#### `aws_region` (takes precedence over `AWS_REGION`)
- The region to create the instance in

#### `instance_type`
- Type of ec2 instance, defaults to: `t2.medium`

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
 - list of paths to watch by `rd sync`

#### `volume_size`
 - defaults to: `30` (GB)
 - Size of the ec2 volume.

 If you update `volume_size` after your instance has been created, then do this to update:
 ```
rd update
rd ssh "sudo growpart /dev/xvda 1 && sudo resize2fs /dev/xvda1"
```

 Profiles are a way to organize and override settings for different projects.

 All the config settings are the same and profile values are prioritized:
 lists are appended and dicts are shallow-merged, otherwise the profile value is used


## Cost
A t2.medium instance on ca-central-1 currently costs $0.051 /hour. [See current prices](https://aws.amazon.com/ec2/pricing/on-demand/)

Nothing else used should incur any cost with reasonable usage, and so far for my usage -- however, please monitor!

## Notes
- See `rd --help` for more information on the commands available

