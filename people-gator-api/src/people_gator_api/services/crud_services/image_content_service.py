"""Image-content retrieval backed by object storage.

Binary image files live in the bucket under::

    image/{website}/{path/to/image.ext}

and are exposed through :func:`get_image_content`, which normalizes and
validates the storage path, downloads the bytes, and resolves the media type
from the extension.
"""

import logging
import mimetypes
import posixpath
from urllib.parse import urlparse
from botocore.exceptions import ClientError

from people_gator_api.services.crud_services.source_service import SourceResolutionError
from people_gator_api.services.s3_filesystem import read_bytes


logger = logging.getLogger(__name__)

_IMAGE_CONTENT_PREFIX = "images"

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


async def get_image_content(
    url: str,
) -> tuple[bytes, str]:
    """Download one stored image and return ``(bytes, media_type)``."""
    parsed_url = urlparse(url)
    key = f"{_IMAGE_CONTENT_PREFIX}/{parsed_url.netloc}{parsed_url.path}"
    try:
        content = await read_bytes(key)
    except ClientError as exc:
        logger.info("image content not found", extra={"key": key})
        raise SourceResolutionError(
            "Image not found",
            status_code=404,
            code="not_found",
        ) from exc
    return content, image_media_type(key)
