"""Backend-neutral filesystems with lazily loaded adapters."""

from typing import TYPE_CHECKING, Any

from .contracts import FileContext, Filesystem, FilesystemEntry, OpenMode

if TYPE_CHECKING:
    from .local import LocalFilesystem
    from .s3 import S3Filesystem


def __getattr__(name: str) -> Any:
    if name == "LocalFilesystem":
        from .local import LocalFilesystem
        return LocalFilesystem
    if name == "S3Filesystem":
        from . import s3
        return getattr(s3, name)
    raise AttributeError(name)


__all__ = ["FileContext", "Filesystem", "FilesystemEntry", "OpenMode", "LocalFilesystem", "S3Filesystem"]
