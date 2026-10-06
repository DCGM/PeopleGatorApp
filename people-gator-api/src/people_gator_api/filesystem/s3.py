"""S3 implementation of the filesystem contract."""

import fnmatch
from aiobotocore.config import AioConfig
from aiobotocore.session import AioSession
from types_aiobotocore_s3.client import S3Client
from people_gator_api.settings import S3Settings, settings
from .contracts import Filesystem, FilesystemEntry


class S3Filesystem(Filesystem):
    def __init__(self, config: S3Settings | None = None) -> None:
        super().__init__()
        selected = config if config is not None else settings.storage.s3
        if selected is None:
            raise ValueError("S3 filesystem requires storage.s3 configuration")
        self.config = selected

    def _client(self) -> S3Client:
        """Return a configured aiobotocore S3 client context manager."""
        cfg = AioConfig(
            connect_timeout=self.config.timeout_seconds,
            read_timeout=self.config.timeout_seconds,
            retries={"max_attempts": 1},
        )
        return AioSession().create_client(  # type: ignore[attr-defined]
            "s3",
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name=self.config.region,
            endpoint_url=self.config.endpoint_url,
            config=cfg,
        )

    async def read_bytes(self, key: str) -> bytes:
        """Download an S3 object and return its raw bytes."""
        async with self._client() as client:
            response = await client.get_object(
                Bucket=self.config.bucket_name,
                Key=key,
            )
            return await response["Body"].read()

    async def write_bytes(self, key: str, data: bytes) -> None:
        """Upload raw bytes to an S3 object key."""
        async with self._client() as client:
            typed_client: S3Client = client
            await typed_client.put_object(
                Bucket=self.config.bucket_name,
                Key=key,
                Body=data,
            )

    async def lsdir(self, prefix: str = "") -> list[FilesystemEntry]:
        """List the immediate contents of an S3 "directory".

        Uses ``delimiter="/"`` so only the first level below *prefix* is returned —
        sub-keys appear as prefix entries (``is_prefix=True``), matching the
        semantics of ``os.listdir`` on a filesystem.

        ``prefix`` should either be empty (bucket root) or end with ``"/"``::

            entries = await lsdir("models/v2/")
            keys    = [e.key for e in entries if not e.is_prefix]
            subdirs = [e.key for e in entries if e.is_prefix]
        """
        async with self._client() as client:
            typed_client: S3Client = client
            entries: list[FilesystemEntry] = []
            paginator = typed_client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.config.bucket_name,
                Prefix=prefix,
                Delimiter="/",
            ):
                for obj in page.get("Contents", []):
                    key: str = obj.get("Key", "")
                    entries.append(FilesystemEntry(key=key, is_prefix=False, size=obj.get("Size")))
                for cp in page.get("CommonPrefixes", []):
                    prefix_key: str = cp.get("Prefix", "")
                    entries.append(FilesystemEntry(key=prefix_key, is_prefix=True, size=None))
            return entries

    async def glob(self, pattern: str) -> list[FilesystemEntry]:
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

        async with self._client() as client:
            typed_client: S3Client = client
            entries: list[FilesystemEntry] = []
            paginator = typed_client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=self.config.bucket_name,
                Prefix=literal_prefix,
            ):
                for obj in page.get("Contents", []):
                    key: str = obj.get("Key", "")
                    if fnmatch.fnmatch(key, pattern):
                        entries.append(FilesystemEntry(key=key, is_prefix=False, size=obj.get("Size")))
            return entries
