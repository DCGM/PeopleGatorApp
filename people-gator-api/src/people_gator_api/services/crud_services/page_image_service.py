"""Page-image retrieval with an optional local resized-JPEG cache.

The canonical page image lives in object storage under
``image/{website}/{path}`` (see :mod:`image_content_service`).  When the
cache is enabled, resized derivatives (JPEG only) are stored on an explicit
filesystem mount under::

    {mount_path}/{website}/{path}/{width}.jpg

and served directly from disk.  Cache misses are rendered from the original
bytes with Pillow and written back to the mount atomically.
"""

import asyncio
import io
import logging
import os
import posixpath
import tempfile
from urllib.parse import urlparse

from PIL import Image
from pydantic import BaseModel

from people_gator_api.services.crud_services.image_content_service import (
    get_image_content,
)
from people_gator_api.services.crud_services.source_service import SourceResolutionError
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
    """Filesystem path of the cached derivative for one page image."""
    return os.path.join(cache_cfg.mount_path, website, object_path, f"{width}.jpg")


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


def _read_cache(path: str) -> bytes | None:
    """Return cached bytes or ``None`` when the derivative is not stored."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("page image cache read failed", extra={"path": path})
        return None


def _write_cache(path: str, data: bytes) -> None:
    """Atomically write a derivative to the cache mount (best effort)."""
    directory = posixpath.dirname(path)
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    except OSError:
        logger.warning("page image cache write failed", extra={"path": path})


async def get_page_image(
    url: str,
    *,
    width: int | None = None,
) -> PageImageContent:
    """Return one page image, optionally a cached JPEG derivative.

    Without ``width`` the original bytes are streamed from object storage.
    With ``width`` (and the cache enabled) a JPEG derivative is served from
    the filesystem mount, rendered on first request and cached afterwards.
    """
    cache_cfg = settings.page_image_cache
    resolved_width = _resolve_width(cache_cfg, width)

    if resolved_width is None or not cache_cfg.enabled:
        content, media_type = await get_image_content(url)
        return PageImageContent(content=content, media_type=media_type, cache_hit=False)

    parsed = urlparse(url)
    cache_path = _cache_key(
        cache_cfg, parsed.netloc, parsed.path.lstrip("/"), resolved_width
    )
    cached = await asyncio.to_thread(_read_cache, cache_path)
    if cached is not None:
        return PageImageContent(
            content=cached, media_type=_JPEG_MEDIA_TYPE, cache_hit=True
        )

    original, _ = await get_image_content(url)
    rendered = await asyncio.to_thread(
        _render_jpeg, original, resolved_width, cache_cfg.quality
    )
    await asyncio.to_thread(_write_cache, cache_path, rendered)
    return PageImageContent(
        content=rendered, media_type=_JPEG_MEDIA_TYPE, cache_hit=False
    )
