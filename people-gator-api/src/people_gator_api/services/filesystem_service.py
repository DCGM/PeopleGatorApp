"""Configured filesystem provider and FastAPI dependency.

Use get_filesystem directly in services or FilesystemDependency in routes.
The compatibility helpers below resolve the current configuration per operation.
"""

import io
from typing import Annotated, Literal, overload

from fastapi import Depends

from people_gator_api.filesystem.contracts import (
    FileContext, Filesystem, FilesystemEntry, OpenMode,
)
from people_gator_api.settings import settings


def get_filesystem() -> Filesystem:
    """Return the adapter selected by storage settings, without opening clients."""
    config = settings.storage
    if config.backend == "local" and config.local is not None:
        from people_gator_api.filesystem.local import LocalFilesystem
        return LocalFilesystem(config.local.root)
    if config.backend == "s3" and config.s3 is not None:
        from people_gator_api.filesystem.s3 import S3Filesystem
        return S3Filesystem(config.s3)
    raise RuntimeError("No valid filesystem configuration found.")


type FilesystemDependency = Annotated[Filesystem, Depends(get_filesystem)]


async def read_bytes(key: str) -> bytes:
    return await get_filesystem().read_bytes(key)


async def write_bytes(key: str, data: bytes) -> None:
    await get_filesystem().write_bytes(key, data)


@overload
def open_file(path: str, mode: Literal["rb", "wb"] = "rb") -> FileContext[io.BytesIO]: ...

@overload
def open_file(path: str, mode: Literal["r", "w"]) -> FileContext[io.StringIO]: ...


def open_file(path: str, mode: OpenMode = "rb") -> FileContext[io.BytesIO] | FileContext[io.StringIO]:
    return get_filesystem().open_file(path, mode)


async def lsdir(prefix: str = "") -> list[FilesystemEntry]:
    return await get_filesystem().lsdir(prefix)


async def glob(pattern: str) -> list[FilesystemEntry]:
    return await get_filesystem().glob(pattern)


__all__ = [
    "FilesystemDependency", "get_filesystem", "read_bytes", "write_bytes",
    "open_file", "lsdir", "glob",
]
