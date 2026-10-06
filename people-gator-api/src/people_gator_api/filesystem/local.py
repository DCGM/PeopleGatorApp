"""Local filesystem with aiofile content I/O and offloaded metadata operations."""

import asyncio
import fnmatch
import os
import tempfile
from pathlib import Path

from aiofile import AIOFile

from .contracts import Filesystem, FilesystemEntry


class LocalFilesystem(Filesystem):
    def __init__(self, root: str | Path) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()

    def _path(self, key: str) -> Path:
        path = Path(key)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Filesystem keys must be relative and cannot contain '..'")
        resolved = (self.root / path).resolve()
        if not resolved.is_relative_to(self.root):
            raise ValueError("Filesystem key resolves outside the storage root")
        return resolved

    async def read_bytes(self, key: str) -> bytes:
        path = await asyncio.to_thread(self._path, key)
        async with AIOFile(path, "rb") as file:
            return await file.read_bytes()

    async def write_bytes(self, key: str, data: bytes) -> None:
        path = await asyncio.to_thread(self._path, key)

        def prepare() -> Path:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(dir=path.parent, prefix=".filesystem-")
            os.close(fd)
            return Path(name)

        temporary = await asyncio.to_thread(prepare)
        try:
            async with AIOFile(temporary, "wb") as file:
                await file.write(data)
                await file.fsync()
            await asyncio.to_thread(os.replace, temporary, path)
        finally:
            await asyncio.to_thread(temporary.unlink, missing_ok=True)

    def _entry(self, path: Path) -> FilesystemEntry:
        self._path(path.relative_to(self.root).as_posix())
        directory = path.is_dir()
        return FilesystemEntry(
            key=path.relative_to(self.root).as_posix() + ("/" if directory else ""),
            is_prefix=directory,
            size=None if directory else path.stat().st_size,
        )

    async def lsdir(self, prefix: str = "") -> list[FilesystemEntry]:
        def list_entries() -> list[FilesystemEntry]:
            return [self._entry(path) for path in sorted(self._path(prefix).iterdir())]

        return await asyncio.to_thread(list_entries)

    async def glob(self, pattern: str) -> list[FilesystemEntry]:
        def match_entries() -> list[FilesystemEntry]:
            self._path(pattern)
            if not self.root.exists():
                return []
            return [
                self._entry(path) for path in sorted(self.root.rglob("*"))
                if path.is_file() and fnmatch.fnmatch(path.relative_to(self.root).as_posix(), pattern)
            ]

        return await asyncio.to_thread(match_entries)
