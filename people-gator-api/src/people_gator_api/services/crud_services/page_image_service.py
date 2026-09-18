"""Page-image retrieval with an optional S3-backed resized-JPEG cache.

The canonical page image lives under the configured image-content S3 prefix
(see :mod:`image_content_service`).  When the
cache is enabled, resized derivatives (JPEG only) are stored in the configured
S3 bucket under::

    {key_prefix}/{website}/{path}/{width}.jpg

Cache misses are rendered from the original bytes with Pillow and uploaded to
the bucket.
"""

import asyncio
import io
import logging
import posixpath
from urllib.parse import urlparse

from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from pydantic import BaseModel

from people_gator_api.services.crud_services.image_content_service import (
    get_image_content,
)
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
    website: str,
    object_path: str,
    width: int,
) -> str:
    """S3 object key of the cached derivative for one page image."""
    return posixpath.join(
        cache_cfg.key_prefix.strip("/"),
        website,
        object_path.lstrip("/"),
        f"{width}.jpg",
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


async def get_page_image(
    url: str,
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

    if resolved_width is None or not cache_cfg.enabled:
        content, media_type = await get_image_content(url)
        return PageImageContent(content=content, media_type=media_type, cache_hit=False)

    parsed = urlparse(url)
    cache_key = _cache_key(
        cache_cfg, parsed.netloc, parsed.path.lstrip("/"), resolved_width
    )
    cached = await _read_cache(cache_key)
    if cached is not None:
        return PageImageContent(
            content=cached, media_type=_JPEG_MEDIA_TYPE, cache_hit=True
        )

    original, _ = await get_image_content(url)
    rendered = await asyncio.to_thread(
        _render_jpeg, original, resolved_width, cache_cfg.quality
    )
    await _write_cache(cache_key, rendered)
    return PageImageContent(
        content=rendered, media_type=_JPEG_MEDIA_TYPE, cache_hit=False
    )
