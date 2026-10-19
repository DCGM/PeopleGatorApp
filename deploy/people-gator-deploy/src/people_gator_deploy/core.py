"""Private atomic files, stable cross-process locks and cancellable processes."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile


class DeployError(ValueError):
    """An actionable diagnostic safe for public CI output."""


def atomic(path: Path, value: str | bytes):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(value.encode() if isinstance(value, str) else value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        Path(name).unlink(missing_ok=True)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


@contextmanager
def lock(path: Path):
    """Never replace/unlink locks: old and new callers must lock the same inode."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def run(args, *, env=None, input=None, stdin=None, timeout=600):
    """Argument lists only; suppress private output on failure; reap process groups."""
    options = {"stdin": stdin} if stdin is not None else {"stdin": subprocess.PIPE if input is not None else subprocess.DEVNULL}
    process = subprocess.Popen([str(a) for a in args], **options, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    try:
        output, error = process.communicate(input=input, timeout=timeout)
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    if process.returncode:
        raise DeployError(f"{Path(str(args[0])).name} failed (exit {process.returncode}); check private service diagnostics")
    return output


@contextmanager
def cancellation():
    previous = signal.getsignal(signal.SIGTERM)
    def terminate(signum, frame):
        raise KeyboardInterrupt("Operation cancelled")
    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
