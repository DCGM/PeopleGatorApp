"""Async S3 filesystem abstraction backed by aiobotocore.

Read modes yield standard-library file objects so any caller that accepts a
file-like (pandas, json.load, csv.reader, …) works without adaptation:

    async with open_file("data.parquet", mode="rb") as f:
        df = pandas.read_parquet(f)

    async with open_file("report.csv", mode="r") as f:
        reader = csv.DictReader(f)

Write modes buffer locally and upload atomically to S3 when the context exits:

    async with open_file("out.json", mode="w") as f:
        json.dump(payload, f)
"""

from __future__ import annotations

import fnmatch
import io
from dataclasses import dataclass
from typing import Literal, overload

from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession
from types_aiobotocore_s3.client import S3Client

from people_gator_api.settings import settings


type OpenMode = Literal["r", "rb", "w", "wb"]


def _s3_client() -> S3Client:
    """Return a configured aiobotocore S3 client context manager."""
    cfg = AioConfig(
        connect_timeout=settings.storage.s3.timeout_seconds,
        read_timeout=settings.storage.s3.timeout_seconds,
        retries={"max_attempts": 1},
    )
    return AioSession().create_client(  # type: ignore[attr-defined]
        "s3",
        aws_access_key_id=settings.storage.s3.access_key_id,
        aws_secret_access_key=settings.storage.s3.secret_access_key,
        region_name=settings.storage.s3.region,
        endpoint_url=settings.storage.s3.endpoint_url,
        config=cfg,
    )


async def _fetch_bytes(key: str) -> bytes:
    """Download an S3 object and return its raw bytes."""
    async with _s3_client() as client:
        response = await client.get_object(
            Bucket=settings.storage.s3.bucket_name,
            Key=key,
        )
        return await response["Body"].read()


async def read_bytes(key: str) -> bytes:
    """Download an S3 object and return its raw bytes (public helper)."""
    return await _fetch_bytes(key)


async def _upload_bytes(key: str, data: bytes) -> None:
    """Upload raw bytes to an S3 object key."""
    async with _s3_client() as client: 
        typed_client: S3Client = client
        await typed_client.put_object(
            Bucket=settings.storage.s3.bucket_name,
            Key=key,
            Body=data,
        )


class _S3FileContext[_F: io.StringIO | io.BytesIO]:
    """Typed async context manager produced by :func:`open_file`.

    A generic class is used instead of ``@asynccontextmanager`` + ``@overload``
    because that combination cannot propagate narrowed yield types through the
    decorator stack.  ``Generic[_F]`` lets type checkers track exactly which
    ``io`` type the caller receives.
    """

    __slots__ = ("_path", "_mode", "_buf")

    def __init__(self, path: str, mode: OpenMode) -> None:
        super().__init__()
        self._path = path
        self._mode = mode

    async def __aenter__(self) -> _F:
        if self._mode == "rb":
            self._buf: _F = io.BytesIO(await _fetch_bytes(self._path))  # type: ignore[assignment]
        elif self._mode == "r":
            self._buf = io.StringIO((await _fetch_bytes(self._path)).decode())  # type: ignore[assignment]
        elif self._mode == "wb":
            self._buf = io.BytesIO()  # type: ignore[assignment]
        else:  # "w"
            self._buf = io.StringIO()  # type: ignore[assignment]
        return self._buf

    async def __aexit__(self, *_: object) -> None:
        if self._mode not in ("w", "wb"):
            return
        if isinstance(self._buf, io.StringIO):
            self._buf.seek(0)
            await _upload_bytes(self._path, self._buf.read().encode())
        else:
            self._buf.seek(0)
            await _upload_bytes(self._path, self._buf.read())


@overload
def open_file(path: str, mode: Literal["rb"]) -> _S3FileContext[io.BytesIO]: ...
@overload
def open_file(path: str, mode: Literal["r"]) -> _S3FileContext[io.StringIO]: ...
@overload
def open_file(path: str, mode: Literal["wb"]) -> _S3FileContext[io.BytesIO]: ...
@overload
def open_file(path: str, mode: Literal["w"]) -> _S3FileContext[io.StringIO]: ...


def open_file(path: str, mode: OpenMode = "rb") -> _S3FileContext[io.BytesIO] | _S3FileContext[io.StringIO]:
    """Async context manager for reading or writing a file on S3.

    Yields a standard-library ``io.BytesIO`` or ``io.StringIO`` so any library
    accepting a file-like (pandas, json, csv, …) works without adaptation.

    The *path* is the S3 object key; bucket and credentials come from settings.
    Write modes buffer locally and upload atomically when the context exits.
    """
    return _S3FileContext(path, mode)


@dataclass(frozen=True)
class S3Entry:
    """A single entry returned by :func:`lsdir` or :func:`glob`.

    *key* is the full S3 object key.
    *is_prefix* is ``True`` for "directory" placeholders (CommonPrefixes),
    ``False`` for actual objects.
    *size* is the object size in bytes; ``None`` for prefixes.
    """

    key: str
    is_prefix: bool
    size: int | None


async def lsdir(prefix: str = "") -> list[S3Entry]:
    """List the immediate contents of an S3 "directory".

    Uses ``delimiter="/"`` so only the first level below *prefix* is returned —
    sub-keys appear as prefix entries (``is_prefix=True``), matching the
    semantics of ``os.listdir`` on a filesystem.

    ``prefix`` should either be empty (bucket root) or end with ``"/"``::

        entries = await lsdir("models/v2/")
        keys    = [e.key for e in entries if not e.is_prefix]
        subdirs = [e.key for e in entries if e.is_prefix]
    """
    async with _s3_client() as client:
        typed_client: S3Client = client
        entries: list[S3Entry] = []
        paginator = typed_client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(
            Bucket=settings.storage.s3.bucket_name,
            Prefix=prefix,
            Delimiter="/",
        ):
            for obj in page.get("Contents", []):
                key: str = obj.get("Key", "")
                entries.append(S3Entry(key=key, is_prefix=False, size=obj.get("Size")))
            for cp in page.get("CommonPrefixes", []):
                prefix_key: str = cp.get("Prefix", "")
                entries.append(S3Entry(key=prefix_key, is_prefix=True, size=None))
        return entries


async def glob(pattern: str) -> list[S3Entry]:
    """Return all S3 objects whose key matches *pattern*.

    *pattern* follows :mod:`fnmatch` rules (``*``, ``?``, ``[seq]``) and is
    matched against the full object key.  Unlike :func:`lsdir`, this lists
    **all** objects recursively under the longest literal prefix of *pattern*
    and then filters client-side::

        parquet_files = await glob("datasets/*/train/*.parquet")
        configs       = await glob("models/v?.json")

    Only actual objects are returned (no prefix entries).
    """
    # Derive the longest literal prefix to narrow the S3 listing.
    literal_prefix = ""
    for char in pattern:
        if char in ("*", "?", "["):
            break
        literal_prefix += char

    async with _s3_client() as client:
        typed_client: S3Client = client
        entries: list[S3Entry] = []
        paginator = typed_client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(
            Bucket=settings.storage.s3.bucket_name,
            Prefix=literal_prefix,
        ):
            for obj in page.get("Contents", []):
                key: str = obj.get("Key", "")
                if fnmatch.fnmatch(key, pattern):
                    entries.append(S3Entry(key=key, is_prefix=False, size=obj.get("Size")))
        return entries

