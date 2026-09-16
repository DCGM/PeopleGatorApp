"""Service for page-layout upload and retrieval backed by object storage.

A page layout (PERO OCR structure) is stored as one JSON document per page
Source.  The storage key is derived from the page Source's archive identity::

    page-layouts/{library}/{document_id}/{page_id}.json

Both selector styles are supported — a raw ``source_id`` and the canonical
archive path (``library/page_id`` or ``library/document_id/page_id``) — and
both the uploaded payload and the stored document are validated with
:class:`~people_gator_api.schemas.pero.PageLayoutModel`.
"""

import logging
import uuid

from botocore.exceptions import ClientError
from pydantic import ValidationError
from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.pero import PageLayoutModel
from people_gator_api.schemas.sources import PageSourceMetadata, SourceResponse
from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
    get_source,
    resolve_source_filter,
)
from people_gator_api.services.s3_filesystem import open_file
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)

_LAYOUT_PREFIX = "page-layouts"


def page_layout_key(source: SourceResponse) -> str:
    """Return the canonical storage key for one page source's layout."""
    metadata = source.metadata
    if not isinstance(metadata, PageSourceMetadata):
        raise SourceResolutionError(
            "page layouts require a page source",
            status_code=422,
            code="invalid_page_layout_source",
        )
    return (
        f"{_LAYOUT_PREFIX}/{metadata.library}"
        f"/{metadata.document}/{metadata.page}.json"
    )


@trace()
async def resolve_page_source(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    page_path: str | None,
) -> SourceResponse:
    """Resolve exactly one selector to a page Source record.

    * ``source_id`` — the internal Source UUID.
    * ``page_path`` — ``library/page_id`` or ``library/document_id/page_id``.
    """
    if (source_id is None) == (page_path is None):
        raise SourceResolutionError(
            "provide exactly one of source_id or page",
            status_code=422,
            code="invalid_page_layout_selector",
        )
    resolved_id = await resolve_source_filter(
        client,
        source_id=source_id,
        page=page_path,
        document=None,
        image=None,
    )
    if resolved_id is None:
        raise SourceResolutionError(
            "provide source_id or page",
            status_code=422,
            code="invalid_page_layout_selector",
        )
    source = await get_source(client, resolved_id)
    if source is None:
        raise SourceResolutionError(
            "Source not found",
            status_code=404,
            code="not_found",
        )
    return source


@trace()
async def get_page_layout(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    page_path: str | None,
) -> PageLayoutModel:
    """Load the stored layout for one page and validate it before returning."""
    source = await resolve_page_source(
        client,
        source_id=source_id,
        page_path=page_path,
    )
    key = page_layout_key(source)
    try:
        async with open_file(key, mode="r") as f:
            raw = f.read()
    except ClientError as exc:
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
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    page_path: str | None,
    layout: PageLayoutModel,
) -> PageLayoutModel:
    """Atomically store the validated layout for one page."""
    source = await resolve_page_source(
        client,
        source_id=source_id,
        page_path=page_path,
    )
    key = page_layout_key(source)
    payload = layout.model_dump_json(indent=2)
    try:
        async with open_file(key, mode="w") as f:
            f.write(payload)
    except ClientError as exc:
        logger.exception("failed to upload page layout", extra={"key": key})
        raise SourceResolutionError(
            "Failed to store page layout",
            status_code=502,
            code="storage_error",
        ) from exc
    logger.info("page layout stored", extra={"key": key})
    return layout
