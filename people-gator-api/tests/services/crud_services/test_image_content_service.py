from __future__ import annotations

import os

os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_SECURE", "false")

import asyncio

import pytest
from botocore.exceptions import ClientError

from people_gator_api.services.crud_services import image_content_service
from people_gator_api.services.crud_services.image_content_service import (
    get_image_content,
    image_content_key,
    image_media_type,
)
from people_gator_api.settings import ImageContentSettings


_URL = "https://example.org/mzk/d/x/img.png"


def test_image_content_key_uses_configured_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        image_content_service.settings,
        "image_content",
        ImageContentSettings(key_prefix="originals/images"),
    )

    assert image_content_key(_URL) == "originals/images/example.org/mzk/d/x/img.png"


def test_image_media_type_from_extension() -> None:
    assert image_media_type("image/mzk/a/b.jpg") == "image/jpeg"
    assert image_media_type("image/mzk/a/b.png") == "image/png"
    assert image_media_type("image/mzk/a/b.tif") == "image/tiff"


def test_get_image_content_missing_object_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_read_bytes(_key: str) -> bytes:
        raise ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
            "GetObject",
        )

    monkeypatch.setattr(image_content_service, "read_bytes", fake_read_bytes)

    with pytest.raises(image_content_service.SourceResolutionError) as exc_info:
        asyncio.run(get_image_content(_URL))
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


def test_get_image_content_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_read_bytes(key: str) -> bytes:
        captured["key"] = key
        return b"\x89PNG\r\n\x1a\nfake-bytes"

    monkeypatch.setattr(image_content_service, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(
        image_content_service.settings,
        "image_content",
        ImageContentSettings(key_prefix="originals/images"),
    )

    content, media_type = asyncio.run(get_image_content(_URL))
    assert captured["key"] == "originals/images/example.org/mzk/d/x/img.png"
    assert content == b"\x89PNG\r\n\x1a\nfake-bytes"
    assert media_type == "image/png"
