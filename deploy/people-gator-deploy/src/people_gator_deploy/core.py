"""Private atomic files, stable cross-process locks and cancellable processes."""
from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
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
def lock(path: Path, *, shared=False):
    """Never replace/unlink locks: old and new callers must lock the same inode.

    Shared holders run concurrently with each other but never with an exclusive
    holder, such as an infrastructure upgrade or a legacy controller.
    """
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
        yield


def run(args, *, env=None, input=None, stdin=None, timeout=600, diagnostic=None, echo=False, progress=None):
    """Argument lists only; suppress private output on failure; reap process groups.

    ``diagnostic`` receives failed output in a private file. ``echo`` relays it
    only for commands known to process synthetic data and no secret input.
    ``progress`` streams stderr into a private file an operator can follow.
    """
    options: dict = {"stdin": stdin} if stdin is not None else {"stdin": subprocess.PIPE if input is not None else subprocess.DEVNULL}
    stream = None
    if progress is not None:
        Path(progress).parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        stream = open(os.open(progress, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600), "w")
    try:
        process = subprocess.Popen([str(a) for a in args], **options, stdout=subprocess.PIPE,
                                   stderr=stream or subprocess.PIPE, text=True, env=env, start_new_session=True)
    except BaseException:
        if stream:
            stream.close()
        raise
    try:
        output, error = process.communicate(input=input, timeout=timeout)
        error = error or ""
    except BaseException:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
        raise
    finally:
        if stream:
            stream.close()
    if process.returncode:
        if diagnostic is not None:
            atomic(Path(diagnostic), output + error)
        if echo and input is None:
            print(output, end="")
            print(error, end="", file=sys.stderr)
        location = f" ({diagnostic})" if diagnostic is not None else ""
        raise DeployError(f"{Path(str(args[0])).name} failed (exit {process.returncode}); "
                          f"check private service diagnostics{location}")
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
