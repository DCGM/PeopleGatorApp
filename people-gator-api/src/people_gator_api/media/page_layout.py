"""Page-layout storage addressed by canonical archive identity.

This module deliberately has no database or persistence-client dependency.
Callers resolve a page once, then pass its ``library``, ``document_id`` and
``page_id`` to the object-storage operation.
"""

import logging
import posixpath
import uuid

from botocore.exceptions import BotoCoreError, ClientError
from pydantic import ValidationError

from people_gator_api.schemas.pero import PageLayoutModel
from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.services.filesystem_service import open_file
from people_gator_api.settings import settings
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)


def page_layout_key(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> str:
    """Return the object-storage key for one page's OCR layout."""
    return posixpath.join(
        settings.page_layout.key_prefix.strip("/"),
        library,
        str(document_id),
        f"{page_id}.json",
    )


@trace()
async def get_page_layout(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> PageLayoutModel:
    """Load and validate one page layout directly from object storage."""
    key = page_layout_key(library, document_id, page_id)
    try:
        async with open_file(key, mode="r") as f:
            raw = f.read()
    except (ClientError, FileNotFoundError) as exc:
        logger.info("page layout not found", extra={"key": key})
        raise SourceResolutionError(
            "Page layout not found",
            status_code=404,
            code="not_found",
        ) from exc
    try:
        return PageLayoutModel.model_validate_json(raw)
    except ValidationError as exc:
        logger.exception("stored page layout failed validation", extra={"key": key})
        raise SourceResolutionError(
            "Stored page layout is invalid",
            status_code=500,
            code="invalid_stored_page_layout",
        ) from exc


@trace()
async def put_page_layout(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    layout: PageLayoutModel,
) -> int:
    """Store one validated layout, returning its serialized UTF-8 byte size."""
    key = page_layout_key(library, document_id, page_id)
    payload = layout.model_dump_json(indent=2)
    try:
        async with open_file(key, mode="w") as f:
            f.write(payload)
    except (ClientError, BotoCoreError, OSError) as exc:
        logger.exception("failed to upload page layout", extra={"key": key})
        raise SourceResolutionError(
            "Failed to store page layout",
            status_code=502,
            code="storage_error",
        ) from exc
    logger.info("page layout stored", extra={"key": key})
    return len(payload.encode("utf-8"))
