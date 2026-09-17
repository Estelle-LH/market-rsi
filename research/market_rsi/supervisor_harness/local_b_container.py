"""Local Docker boundary for B's zero-paid synthetic transport canary.

This adapter is deliberately not an empirical runner. The trusted host owns
the broker, evaluator and all credentials; only the standalone guest worker is
mounted into the container. A running Docker daemon and a live isolation test
are required before this is treated as a sandbox, not just a command recipe.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path


IMAGE = "python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea"
GUEST_PATH = "/opt/market-rsi/directional_guest_worker.py"
WORK_PATH = "/work/directional"
GUEST_ROOT = "/tmp/market-researcher/directional"
_GUEST_FILE = re.compile(r"/(orders|acks|events)/([0-9]{3})\.json\Z")


class LocalBFiles:
    """Broker file view; rejects guest paths outside the one B mount."""

    def __init__(self, work: Path):
        work = Path(work)
        if work.is_symlink():
            raise ValueError("invalid B work mount")
        self.work = work.resolve(strict=True)
        if not self.work.is_dir():
            raise ValueError("invalid B work mount")
        self.root_fd = os.open(self.work, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self) -> None:
        if self.root_fd is not None:
            os.close(self.root_fd)
            self.root_fd = None

    def _directory_fd(self, name: str, *, create: bool = False) -> int:
        if self.root_fd is None:
            raise ValueError("B file view is closed")
        if create:
            try:
                os.mkdir(name, mode=0o700, dir_fd=self.root_fd)
            except FileExistsError:
                pass
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                       dir_fd=self.root_fd)

    def _path(self, guest_path: str) -> tuple[str, str]:
        if not isinstance(guest_path, str) or not guest_path.startswith(GUEST_ROOT):
            raise ValueError("B path outside work mount")
        match = _GUEST_FILE.fullmatch(guest_path[len(GUEST_ROOT):])
        if match is None:
            raise ValueError("B path is not an allowed canary artifact")
        return match.group(1), f"{match.group(2)}.json"

    def write(self, guest_path: str, value: str) -> None:
        directory, name = self._path(guest_path)
        if directory != "orders" or not isinstance(value, str):
            raise ValueError("host may only publish bounded orders")
        raw = value.encode("utf-8")
        if not 0 < len(raw) <= 64 * 1024:
            raise ValueError("oversized order")
        orders_fd = self._directory_fd("orders", create=True)
        try:
            stage_fd = self._directory_fd("staging", create=True)
            try:
                temporary = f".{name}.tmp"
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=stage_fd)
                try:
                    with os.fdopen(fd, "wb") as output:
                        output.write(raw)
                        output.flush()
                        os.fsync(output.fileno())
                    os.link(temporary, name, src_dir_fd=stage_fd,
                            dst_dir_fd=orders_fd, follow_symlinks=False)
                    os.fsync(orders_fd)
                finally:
                    os.unlink(temporary, dir_fd=stage_fd)
            finally:
                os.close(stage_fd)
        finally:
            os.close(orders_fd)

    def read(self, guest_path: str) -> str:
        directory, name = self._path(guest_path)
        if directory not in {"acks", "events"}:
            raise ValueError("host may only read B result files")
        directory_fd = self._directory_fd(directory)
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 64 * 1024:
                    raise ValueError("unsafe B result file")
                raw = os.read(fd, 64 * 1024 + 1)
                if len(raw) != info.st_size:
                    raise ValueError("B result changed while reading")
                return raw.decode("utf-8")
            finally:
                os.close(fd)
        finally:
            os.close(directory_fd)


def docker_command(*, container_name: str, source: Path, work: Path,
                   uid: int | None = None, gid: int | None = None) -> list[str]:
    """Build a least-privilege, no-network command for one persistent B worker."""
    if not container_name.startswith("market-rsi-b-") or not all(
        c.isascii() and (c.isalnum() or c in "-_") for c in container_name
    ):
        raise ValueError("invalid B container name")
    source = Path(source)
    work = Path(work)
    if source.is_symlink() or work.is_symlink():
        raise ValueError("B mount paths must not be symlinks")
    source = source.resolve(strict=True)
    work = work.resolve(strict=True)
    if not source.is_file():
        raise ValueError("guest source must be a regular file")
    if not work.is_dir() or source.is_relative_to(work):
        raise ValueError("fresh work directory must be separate from source")
    if any(work.iterdir()):
        raise ValueError("B work directory must be empty")
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    if uid <= 0 or gid <= 0:
        raise ValueError("B must not run as root")
    return [
        "docker", "run", "--rm", "--pull", "never", "--name", container_name,
        "--label", f"market-rsi-canary={container_name}",
        "--network", "none", "--read-only", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--memory", "512m", "--cpus", "1", "--user", f"{uid}:{gid}",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
        "--mount", f"type=bind,src={source},dst={GUEST_PATH},readonly",
        "--mount", f"type=bind,src={work},dst={WORK_PATH}",
        "--workdir", "/work", IMAGE, "python", "-I", GUEST_PATH,
        "--root", WORK_PATH, "--per-order-timeout", "10",
        "--total-timeout", "120",
    ]


def docker_ready(*, run=subprocess.run) -> bool:
    """Read-only readiness check; never pull an image or start a container."""
    try:
        result = run(["docker", "version", "--format", "{{.Server.Version}}"],
                     capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and bool(result.stdout.strip())


def main() -> int:
    if docker_ready():
        print("Docker engine ready; no container dispatched")
        return 0
    print("Docker engine unavailable; local B canary remains blocked", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
