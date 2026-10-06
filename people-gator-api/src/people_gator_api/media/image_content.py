"""Image-content retrieval backed by object storage.

Binary image files live in the bucket under::

    {key_prefix}/{website}/{path/to/image.ext}

and are exposed through :func:`get_image_content`, which derives the storage
key from the URL, downloads the bytes, and resolves the media type from the
extension.
"""

import logging
import mimetypes
import posixpath
from urllib.parse import urlparse
from botocore.exceptions import ClientError

from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.services.filesystem_service import read_bytes
from people_gator_api.settings import settings


logger = logging.getLogger(__name__)

# Explicit allow-list; mimetypes is only used to map extensions to media types.
_ALLOWED_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
)

_FALLBACK_MEDIA_TYPE = "application/octet-stream"


def image_media_type(key: str) -> str:
    """Resolve the response media type from the object key extension."""
    extension = posixpath.splitext(key)[1].lower()
    guessed = mimetypes.types_map.get(extension)
    if guessed is not None:
        return guessed
    if extension in (".tif", ".tiff"):
        return "image/tiff"
    return _FALLBACK_MEDIA_TYPE


def image_content_key(url: str) -> str:
    """Return the configured S3 object key for one image URL."""
    parsed_url = urlparse(url)
    return posixpath.join(
        settings.image_content.key_prefix.strip("/"),
        parsed_url.netloc,
        parsed_url.path.lstrip("/"),
    )


async def get_image_content(
    url: str,
) -> tuple[bytes, str]:
    """Download one stored image and return ``(bytes, media_type)``."""
    key = image_content_key(url)
    try:
        content = await read_bytes(key)
    except (ClientError, FileNotFoundError) as exc:
        logger.info("image content not found", extra={"key": key})
        raise SourceResolutionError(
            "Image not found",
            status_code=404,
            code="not_found",
        ) from exc
    return content, image_media_type(key)
