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
import io

import pytest
from PIL import Image

from people_gator_api.services.crud_services import page_image_service
from people_gator_api.services.crud_services.page_image_service import (
    PageImageContent,
    get_page_image,
)
from people_gator_api.settings import PageImageCacheSettings


_URL = "https://example.org/mzk/d/x/img.png"


def _png_bytes(width: int = 400, height: int = 200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 10, 10)).save(
        buffer, format="PNG"
    )
    return buffer.getvalue()


def _enable_cache(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> PageImageCacheSettings:
    cache_cfg = PageImageCacheSettings(
        enabled=True,
        mount_path=str(tmp_path),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(page_image_service.settings, "page_image_cache", cache_cfg)
    return cache_cfg


def _stub_original(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    async def fake_get_image_content(_url: str) -> tuple[bytes, str]:
        return data, "image/png"

    monkeypatch.setattr(
        page_image_service, "get_image_content", fake_get_image_content
    )


def test_get_page_image_without_width_streams_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.Path
) -> None:
    _enable_cache(monkeypatch, tmp_path)
    _stub_original(monkeypatch, b"original-bytes")

    result = asyncio.run(get_page_image(_URL))

    assert result == PageImageContent(
        content=b"original-bytes", media_type="image/png", cache_hit=False
    )


def test_get_page_image_rejects_unknown_width(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.Path
) -> None:
    cache_cfg = _enable_cache(monkeypatch, tmp_path)

    with pytest.raises(page_image_service.SourceResolutionError) as exc_info:
        asyncio.run(get_page_image(_URL, max_width=cache_cfg.widths[0] + 1))
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_image_width"


def test_get_page_image_renders_and_caches_derivative(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.Path
) -> None:
    cache_cfg = _enable_cache(monkeypatch, tmp_path)
    _stub_original(monkeypatch, _png_bytes())

    first = asyncio.run(get_page_image(_URL, max_width=cache_cfg.widths[0]))
    assert first.media_type == "image/jpeg"
    assert first.cache_hit is False

    # The derivative is stored on the mount and served as a cache hit.
    cached_path = (
        tmp_path
        / "example.org"
        / "mzk"
        / "d"
        / "x"
        / "img.png"
        / f"{cache_cfg.widths[0]}.jpg"
    )
    assert cached_path.is_file()

    second = asyncio.run(get_page_image(_URL, max_width=cache_cfg.widths[0]))
    assert second.cache_hit is True
    assert second.media_type == first.media_type
    assert second.content == first.content

    with Image.open(io.BytesIO(second.content)) as img:
        assert img.width == cache_cfg.widths[0]
        assert img.height == 128  # aspect preserved from 400x200


def test_get_page_image_disabled_cache_streams_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pytest.Path
) -> None:
    _stub_original(monkeypatch, b"original-bytes")

    result = asyncio.run(get_page_image(_URL, max_width=256))

    assert result.content == b"original-bytes"
    assert result.cache_hit is False
