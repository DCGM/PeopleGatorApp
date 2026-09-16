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
    image_media_type,
    normalize_image_key,
)


def test_normalize_image_key_builds_canonical_key() -> None:
    key = normalize_image_key("mzk", "path/to/image.jpg")
    assert key == "image/mzk/path/to/image.jpg"


def test_normalize_image_key_rejects_traversal() -> None:
    with pytest.raises(image_content_service.SourceResolutionError) as exc_info:
        normalize_image_key("mzk", "../../etc/passwd.jpg")
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_image_path"


def test_normalize_image_key_rejects_empty_segments() -> None:
    with pytest.raises(image_content_service.SourceResolutionError):
        normalize_image_key("mzk", "a//b.jpg")
    with pytest.raises(image_content_service.SourceResolutionError):
        normalize_image_key("mzk", "")


def test_normalize_image_key_rejects_unknown_extension() -> None:
    with pytest.raises(image_content_service.SourceResolutionError) as exc_info:
        normalize_image_key("mzk", "docs/report.pdf")
    assert exc_info.value.code == "invalid_image_path"


def test_normalize_image_key_accepts_uppercase_extension() -> None:
    key = normalize_image_key("mzk", "a/b.JPG")
    assert key == "image/mzk/a/b.JPG"


def test_image_media_type_from_extension() -> None:
    assert image_media_type("image/mzk/a/b.jpg") == "image/jpeg"
    assert image_media_type("image/mzk/a/b.png") == "image/png"
    assert image_media_type("image/mzk/a/b.tif") == "image/tiff"


def test_install_fake_s3_missing_object(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_read_bytes(_key: str) -> bytes:
        raise ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
            "GetObject",
        )

    monkeypatch.setattr(image_content_service, "read_bytes", fake_read_bytes)

    with pytest.raises(image_content_service.SourceResolutionError) as exc_info:
        asyncio.run(get_image_content("mzk", "missing/image.jpg"))
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


def test_get_image_content_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str] = {}

    async def fake_read_bytes(key: str) -> bytes:
        captured["key"] = key
        return b"\x89PNG\r\n\x1a\nfake-bytes"

    monkeypatch.setattr(image_content_service, "read_bytes", fake_read_bytes)

    content, media_type = asyncio.run(get_image_content("mzk", "d/x/img.png"))
    assert captured["key"] == "image/mzk/d/x/img.png"
    assert content == b"\x89PNG\r\n\x1a\nfake-bytes"
    assert media_type == "image/png"


def test_get_image_content_rejects_bad_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fail_read_bytes(_key: str) -> bytes:
        raise AssertionError("should not be called")

    monkeypatch.setattr(image_content_service, "read_bytes", fail_read_bytes)

    with pytest.raises(image_content_service.SourceResolutionError):
        asyncio.run(get_image_content("mzk", "../secret.jpg"))
