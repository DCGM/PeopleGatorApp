from contextlib import asynccontextmanager
from typing import AsyncGenerator, cast

import aioboto3
from types_aiobotocore_s3 import S3Client

from people_gator_api.settings import S3Settings, settings

_session: aioboto3.Session | None = None
_bucket: str | None = None


def _s3_settings() -> S3Settings:
    return settings.storage.s3


@asynccontextmanager
async def _client() -> AsyncGenerator[S3Client, None]:
    """Internal context manager that yields a typed S3 client."""
    assert _session is not None, "S3 not initialised — call init_s3() first"
    s3_settings = _s3_settings()
    async with _session.client(  # type: ignore[attr-defined]
        "s3",
        region_name=s3_settings.region,
        endpoint_url=s3_settings.endpoint_url,
        aws_access_key_id=s3_settings.access_key_id,
        aws_secret_access_key=s3_settings.secret_access_key,
    ) as client:  # type: ignore[misc]  # aioboto3 client() has no typed __aenter__
        yield cast(S3Client, client)


async def init_s3() -> None:
    """Initialise the module-level S3 session and verify bucket access."""
    global _session, _bucket
    s3_settings = _s3_settings()
    _session = aioboto3.Session()
    _bucket = s3_settings.bucket_name
    async with _client() as client:
        await client.head_bucket(Bucket=_bucket)


async def put_object(key: str, body: bytes, content_type: str = "application/octet-stream") -> None:
    """Upload *body* to *key* in the configured bucket."""
    assert _bucket is not None
    async with _client() as client:
        await client.put_object(Bucket=_bucket, Key=key, Body=body, ContentType=content_type)


async def get_object(key: str) -> bytes:
    """Download and return the raw bytes at *key* from the configured bucket."""
    assert _bucket is not None
    async with _client() as client:
        response = await client.get_object(Bucket=_bucket, Key=key)
        return await response["Body"].read()


async def delete_object(key: str) -> None:
    """Delete the object at *key* from the configured bucket."""
    assert _bucket is not None
    async with _client() as client:
        await client.delete_object(Bucket=_bucket, Key=key)


async def list_objects(prefix: str = "") -> list[str]:
    """Return all keys under *prefix* in the configured bucket."""
    assert _bucket is not None
    keys: list[str] = []
    async with _client() as client:
        paginator = client.get_paginator("list_objects_v2")
        async for page in paginator.paginate(Bucket=_bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if key := obj.get("Key"):
                    keys.append(key)
    return keys


async def generate_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Return a pre-signed GET URL for *key*, valid for *expires_in* seconds."""
    assert _bucket is not None
    async with _client() as client:
        return await client.generate_presigned_url(
            "get_object",
            Params={"Bucket": _bucket, "Key": key},
            ExpiresIn=expires_in,
        )
