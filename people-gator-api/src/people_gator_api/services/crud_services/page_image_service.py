"""Page-scan retrieval with an optional S3-backed resized-JPEG cache.

Original page scans are addressed only by their canonical archive identity and
live in object storage under::

    {scan_prefix}/{library}/{document_id}/{page_id}.jpg

When the cache is enabled, resized derivatives (JPEG only) are stored under::

    {cache_prefix}/{library}/{document_id}/{page_id}/{width}.jpg

Cache misses are rendered from the original bytes with Pillow and uploaded to
the bucket.
"""

import asyncio
import io
import logging
import posixpath
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from pydantic import BaseModel

from people_gator_api.services.crud_services.source_service import SourceResolutionError
from people_gator_api.services.s3_filesystem import read_bytes, write_bytes
from people_gator_api.settings import PageImageCacheSettings, settings


logger = logging.getLogger(__name__)

_JPEG_MEDIA_TYPE = "image/jpeg"


class PageImageContent(BaseModel):
    """One rendered page image ready for an HTTP response."""

    content: bytes
    media_type: str
    cache_hit: bool


def _cache_key(
    cache_cfg: PageImageCacheSettings,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    width: int,
) -> str:
    """S3 object key of the cached derivative for one page image."""
    return posixpath.join(
        cache_cfg.key_prefix.strip("/"),
        library,
        str(document_id),
        str(page_id),
        f"{width}.jpg",
    )


def page_image_key(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> str:
    """Return the canonical object-storage key for one original page scan."""
    return posixpath.join(
        settings.page_image.key_prefix.strip("/"),
        library,
        str(document_id),
        f"{page_id}.jpg",
    )


def _resolve_width(
    cache_cfg: PageImageCacheSettings,
    width: int | None,
) -> int | None:
    """Validate the requested width against the configured allow-list."""
    if width is None:
        return None
    if width not in cache_cfg.widths:
        raise SourceResolutionError(
            "unsupported image width",
            status_code=422,
            code="invalid_image_width",
        )
    return width


def _render_jpeg(data: bytes, width: int, quality: int) -> bytes:
    """Resize an image to ``width`` (aspect preserved) and encode as JPEG."""
    with Image.open(io.BytesIO(data)) as img:
        ratio = width / img.width
        target: tuple[int, int] = (width, max(1, round(img.height * ratio)))
        resized: Image.Image = img.resize(target)  # pyright: ignore[reportUnknownMemberType]
        if resized.mode not in ("RGB", "L"):
            resized = resized.convert("RGB")
        buffer = io.BytesIO()
        resized.save(buffer, format="JPEG", quality=quality)
        return buffer.getvalue()


def _is_missing_object(exc: ClientError) -> bool:
    code = exc.response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "NotFound"}


async def _read_cache(key: str) -> bytes | None:
    """Return cached bytes or ``None`` when the derivative is not stored."""
    try:
        return await read_bytes(key)
    except ClientError as exc:
        if not _is_missing_object(exc):
            logger.warning("page image cache read failed", extra={"key": key})
        return None
    except BotoCoreError:
        logger.warning("page image cache read failed", extra={"key": key})
        return None


async def _write_cache(key: str, data: bytes) -> None:
    """Upload a derivative to the cache prefix (best effort)."""
    try:
        await write_bytes(key, data)
    except BotoCoreError:
        logger.warning("page image cache write failed", extra={"key": key})


async def _read_original(key: str) -> bytes:
    """Read an original page scan and translate a missing object to a 404."""
    try:
        return await read_bytes(key)
    except ClientError as exc:
        logger.info("page image not found", extra={"key": key})
        raise SourceResolutionError(
            "Page image not found",
            status_code=404,
            code="not_found",
        ) from exc


async def get_page_image(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    *,
    max_width: int | None = None,
) -> PageImageContent:
    """Return one page image, optionally a cached JPEG derivative.

    Without ``max_width`` the original bytes are streamed from object storage.
    With ``max_width`` (and the cache enabled) a JPEG derivative is served from
    S3, rendered on first request and uploaded to the configured bucket.
    """
    cache_cfg = settings.page_image_cache
    resolved_width = _resolve_width(cache_cfg, max_width)
    original_key = page_image_key(library, document_id, page_id)

    if resolved_width is None or not cache_cfg.enabled:
        content = await _read_original(original_key)
        return PageImageContent(
            content=content,
            media_type=_JPEG_MEDIA_TYPE,
            cache_hit=False,
        )

    cache_key = _cache_key(
        cache_cfg,
        library,
        document_id,
        page_id,
        resolved_width,
    )
    cached = await _read_cache(cache_key)
    if cached is not None:
        return PageImageContent(
            content=cached, media_type=_JPEG_MEDIA_TYPE, cache_hit=True
        )

    original = await _read_original(original_key)
    rendered = await asyncio.to_thread(
        _render_jpeg, original, resolved_width, cache_cfg.quality
    )
    await _write_cache(cache_key, rendered)
    return PageImageContent(
        content=rendered, media_type=_JPEG_MEDIA_TYPE, cache_hit=False
    )
