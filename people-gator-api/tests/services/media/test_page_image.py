from __future__ import annotations

import os

os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")

import asyncio
import io
import uuid
from typing import cast

import pytest
from botocore.exceptions import ClientError
from PIL import Image

from people_gator_api.media import page_image
from people_gator_api.media.page_image import (
    PageImageContent,
    get_page_image,
    page_image_key,
)
from people_gator_api.settings import PageImageCacheSettings, PageImageSettings


_LIBRARY = "mzk"
_DOCUMENT_ID = uuid.UUID("23b44592-98e4-4ad3-b62d-3cfc821abb21")
_PAGE_ID = uuid.UUID("b96c068d-1707-4622-bf64-1c5a8eb26f84")


def _png_bytes(width: int = 400, height: int = 200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color=(200, 10, 10)).save(buffer, format="PNG")
    return buffer.getvalue()


def _enable_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> PageImageCacheSettings:
    cache_cfg = PageImageCacheSettings(
        enabled=True,
        key_prefix="page-image-cache",
    )
    monkeypatch.setattr(page_image.settings, "page_image_cache", cache_cfg)
    return cache_cfg


def _install_fake_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, bytes]:
    objects: dict[str, bytes] = {}

    async def fake_read_bytes(key: str) -> bytes:
        if key not in objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        return objects[key]

    async def fake_write_bytes(key: str, data: bytes) -> None:
        objects[key] = data

    monkeypatch.setattr(page_image, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(page_image, "write_bytes", fake_write_bytes)
    return objects


def _store_original(objects: dict[str, bytes], data: bytes) -> None:
    objects[page_image_key(_LIBRARY, _DOCUMENT_ID, _PAGE_ID)] = data


async def _get_page_image_and_drain(
    *args: object, **kwargs: object
) -> PageImageContent:
    """Await ``get_page_image`` plus its fire-and-forget cache-write task.

    Cache writes are scheduled in the background so the response never waits
    on them; tests still need to observe the write's outcome.
    """
    result = await get_page_image(*args, **kwargs)  # type: ignore[arg-type]
    pending = list(
        page_image._background_cache_writes  # pyright: ignore[reportPrivateUsage]
    )
    if pending:
        await asyncio.gather(*pending)
    return result


def test_page_image_key_uses_configured_scan_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        page_image.settings,
        "page_image",
        PageImageSettings(key_prefix="archive/scans"),
    )

    assert page_image_key(_LIBRARY, _DOCUMENT_ID, _PAGE_ID) == (
        f"archive/scans/{_LIBRARY}/{_DOCUMENT_ID}/{_PAGE_ID}.jpg"
    )


def test_get_page_image_without_width_streams_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_cache(monkeypatch)
    objects = _install_fake_cache(monkeypatch)
    _store_original(objects, b"original-bytes")

    result = asyncio.run(get_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID))

    assert result == PageImageContent(
        content=b"original-bytes", media_type="image/jpeg", cache_hit=False
    )


def test_get_page_image_rejects_unknown_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_cfg = _enable_cache(monkeypatch)

    with pytest.raises(page_image.SourceResolutionError) as exc_info:
        asyncio.run(
            get_page_image(
                _LIBRARY,
                _DOCUMENT_ID,
                _PAGE_ID,
                max_width=cache_cfg.widths[0] + 1,
            )
        )
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_image_width"


def test_get_page_image_renders_and_caches_derivative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_cfg = _enable_cache(monkeypatch)
    objects = _install_fake_cache(monkeypatch)
    _store_original(objects, _png_bytes())

    first = asyncio.run(
        _get_page_image_and_drain(
            _LIBRARY,
            _DOCUMENT_ID,
            _PAGE_ID,
            max_width=cache_cfg.widths[0],
        )
    )
    assert first.media_type == "image/jpeg"
    assert first.cache_hit is False

    # The derivative is stored in S3 and served as a cache hit.
    cache_key = (
        f"page-image-cache/{_LIBRARY}/{_DOCUMENT_ID}/{_PAGE_ID}/"
        f"{cache_cfg.widths[0]}.jpg"
    )
    assert cache_key in objects

    second = asyncio.run(
        get_page_image(
            _LIBRARY,
            _DOCUMENT_ID,
            _PAGE_ID,
            max_width=cache_cfg.widths[0],
        )
    )
    assert second.cache_hit is True
    assert second.media_type == first.media_type
    assert second.content == first.content

    with Image.open(io.BytesIO(second.content)) as img:
        assert img.width == cache_cfg.widths[0]
        assert img.height == 128  # aspect preserved from 400x200


def test_get_page_image_disabled_cache_streams_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_cfg = _enable_cache(monkeypatch)
    monkeypatch.setattr(
        page_image.settings,
        "page_image_cache",
        cache_cfg.model_copy(update={"enabled": False}),
    )
    objects = _install_fake_cache(monkeypatch)
    _store_original(objects, b"original-bytes")

    result = asyncio.run(
        get_page_image(
            _LIBRARY,
            _DOCUMENT_ID,
            _PAGE_ID,
            max_width=256,
        )
    )

    assert result.content == b"original-bytes"
    assert result.cache_hit is False


def test_get_page_image_missing_original_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_cache(monkeypatch)

    with pytest.raises(page_image.SourceResolutionError) as exc_info:
        asyncio.run(get_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID))

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_replacement_waits_for_pending_derivative_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_cfg = _enable_cache(monkeypatch)
    cache_cfg.widths = [256]
    objects = _install_fake_cache(monkeypatch)
    _store_original(objects, _png_bytes())
    cache_key = f"page-image-cache/{_LIBRARY}/{_DOCUMENT_ID}/{_PAGE_ID}/256.jpg"
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_write(key: str, data: bytes) -> None:
        if key == cache_key and not started.is_set():
            started.set()
            await release.wait()
        objects[key] = data

    monkeypatch.setattr(page_image, "write_bytes", delayed_write)
    await get_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID, max_width=256)
    await asyncio.wait_for(started.wait(), timeout=5)
    upload = io.BytesIO()
    Image.new("RGB", (400, 200), "blue").save(upload, format="JPEG")
    lock = page_image._page_lock(  # pyright: ignore[reportPrivateUsage]
        page_image_key(_LIBRARY, _DOCUMENT_ID, _PAGE_ID)
    )
    replacement = asyncio.create_task(page_image.put_page_image(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID, upload.getvalue()
    ))

    async def wait_until_replacement_holds_lock() -> None:
        while not lock.locked():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait_until_replacement_holds_lock(), timeout=5)
    assert not replacement.done()
    assert objects[page_image_key(_LIBRARY, _DOCUMENT_ID, _PAGE_ID)] == _png_bytes()
    release.set()
    await asyncio.wait_for(replacement, timeout=5)

    fetched = await get_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID, max_width=256)
    assert fetched.cache_hit is True
    with Image.open(io.BytesIO(fetched.content)) as image:
        red, _, blue = cast(tuple[int, int, int], image.convert("RGB").getpixel((0, 0)))
        assert blue > red
    assert objects[page_image_key(_LIBRARY, _DOCUMENT_ID, _PAGE_ID)] == upload.getvalue()


@pytest.mark.asyncio
async def test_replacement_refreshes_derivatives_when_cache_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache_cfg = _enable_cache(monkeypatch)
    objects = _install_fake_cache(monkeypatch)
    _store_original(objects, _png_bytes())
    await _get_page_image_and_drain(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID, max_width=256
    )
    cache_cfg.enabled = False
    upload = io.BytesIO()
    Image.new("RGB", (400, 200), "blue").save(upload, format="PNG")
    await page_image.put_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID, upload.getvalue())
    cache_cfg.enabled = True

    fetched = await get_page_image(_LIBRARY, _DOCUMENT_ID, _PAGE_ID, max_width=256)
    assert fetched.cache_hit is True
    with Image.open(io.BytesIO(fetched.content)) as image:
        red, _, blue = cast(tuple[int, int, int], image.convert("RGB").getpixel((0, 0)))
        assert blue > red
