import os
import subprocess


def _configure_docker_for_testcontainers() -> None:
    """Point testcontainers at the active Docker context (e.g. Colima) when DOCKER_HOST is unset."""
    if os.environ.get("DOCKER_HOST"):
        return
    try:
        host = subprocess.run(
            ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return
    if host.startswith("unix://") and host != "unix:///var/run/docker.sock":
        os.environ["DOCKER_HOST"] = host
        # Inside the Docker VM the socket is always at the standard path (used by Ryuk).
        os.environ.setdefault("TESTCONTAINERS_DOCKER_SOCKET_OVERRIDE", "/var/run/docker.sock")


_configure_docker_for_testcontainers()
