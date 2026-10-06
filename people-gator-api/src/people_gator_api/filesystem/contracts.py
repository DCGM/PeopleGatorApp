"""Backend-neutral filesystem contract, using root-relative object keys."""

import io
from abc import ABC, abstractmethod
from dataclasses import dataclass
from types import TracebackType
from typing import Literal, cast, overload


type OpenMode = Literal["r", "rb", "w", "wb"]


@dataclass(frozen=True)
class FilesystemEntry:
    key: str
    is_prefix: bool
    size: int | None


class FileContext[_F: io.StringIO | io.BytesIO]:
    """Buffer file contents while the backend performs asynchronous I/O.

    As in the original S3 implementation, write buffers are committed on exit,
    including when the context body raises. Buffers are closed after exit.
    """

    def __init__(self, filesystem: Filesystem, path: str, mode: OpenMode) -> None:
        super().__init__()
        if cast(str, mode) not in ("r", "rb", "w", "wb"):
            raise ValueError(f"Unsupported file mode: {mode}")
        self._filesystem = filesystem
        self._path = path
        self._mode = mode
        self._buffer: _F

    async def __aenter__(self) -> _F:
        data = await self._filesystem.read_bytes(self._path) if self._mode in ("r", "rb") else b""
        self._buffer = cast(_F, io.BytesIO(data) if "b" in self._mode else io.StringIO(data.decode("utf-8")))
        return self._buffer

    async def __aexit__(
        self, exc_type: type[BaseException] | None,
        exc: BaseException | None, traceback: TracebackType | None,
    ) -> None:
        try:
            if self._mode in ("w", "wb"):
                data = self._buffer.getvalue()
                await self._filesystem.write_bytes(
                    self._path, data.encode("utf-8") if isinstance(data, str) else data,
                )
        finally:
            self._buffer.close()


class Filesystem(ABC):
    """Async byte I/O and listings, with buffered synchronous file handles.

    lsdir returns immediate files and directory prefixes (ending in '/'). glob
    returns only files and matches full keys using fnmatch, including across '/'.
    """

    @abstractmethod
    async def read_bytes(self, key: str) -> bytes: ...

    @abstractmethod
    async def write_bytes(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    async def lsdir(self, prefix: str = "") -> list[FilesystemEntry]: ...

    @abstractmethod
    async def glob(self, pattern: str) -> list[FilesystemEntry]: ...

    @overload
    def open_file(self, path: str, mode: Literal["rb", "wb"] = "rb") -> FileContext[io.BytesIO]: ...

    @overload
    def open_file(self, path: str, mode: Literal["r", "w"]) -> FileContext[io.StringIO]: ...

    def open_file(self, path: str, mode: OpenMode = "rb") -> FileContext[io.BytesIO] | FileContext[io.StringIO]:
        return FileContext(self, path, mode)
