class RemoteDockerException(RuntimeError):
    pass


class InstanceNotRunning(RemoteDockerException):
    pass
