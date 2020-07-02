import subprocess


def test_cli_runs_successfully():
    output = subprocess.check_output("remote-docker-aws --help", shell=True)
    assert output

    output = subprocess.check_output("rd --help", shell=True)
    assert output
