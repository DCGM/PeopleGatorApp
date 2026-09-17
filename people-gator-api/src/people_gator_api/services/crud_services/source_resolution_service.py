"""Resolve public source descriptors and filters through the generic source CRUD API."""

import uuid

from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceDescriptorRequest, SourceResponse
from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
    create_source,
    get_source,
)
from people_gator_api.utils.opentelemetry import trace


def _parse_archive_path(
    value: str,
    *,
    resource: str,
    identifier_counts: tuple[int, ...],
) -> tuple[str, list[uuid.UUID]]:
    parts = value.strip("/").split("/")
    if len(parts) not in {count + 1 for count in identifier_counts} or not parts[0]:
        expected = (
            "library/page_id or library/document_id/page_id"
            if resource == "page"
            else "library/document_id"
        )
        raise SourceResolutionError(
            f"invalid {resource} selector; expected {expected}",
            status_code=422,
            code="invalid_source_filter",
        )
    try:
        return parts[0], [uuid.UUID(part) for part in parts[1:]]
    except ValueError as exc:
        raise SourceResolutionError(
            f"invalid {resource} selector; identifiers must be UUIDs",
            status_code=422,
            code="invalid_source_filter",
        ) from exc


@trace()
async def resolve_source_reference(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    source: SourceDescriptorRequest | None,
) -> SourceResponse:
    if source_id is not None:
        resolved = await get_source(client, source_id)
        if resolved is None:
            raise SourceResolutionError(
                "Source not found", status_code=404, code="not_found"
            )
        return resolved
    if source is None:
        raise SourceResolutionError(
            "provide source_id or source",
            status_code=422,
            code="invalid_source_reference",
        )

    if source.page is not None:
        resolved, _ = await create_source(
            client,
            SourceKind.page,
            library=source.page.library,
            document_id=source.page.document_id,
            page_id=source.page.page_id,
        )
    elif source.document is not None:
        resolved, _ = await create_source(
            client,
            SourceKind.document,
            library=source.document.library,
            document_id=source.document.document_id,
        )
    elif source.image is not None:
        resolved, _ = await create_source(
            client,
            SourceKind.image,
            url=str(source.image.url),
        )
    else:  # Protected by SourceDescriptorRequest validation.
        raise SourceResolutionError(
            "source descriptor requires page, document, or image",
            status_code=422,
            code="invalid_source_reference",
        )
    return resolved


@trace()
async def resolve_source_filter(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    page: str | None,
    document: str | None,
    image: str | None,
) -> uuid.UUID | None:
    if sum(value is not None for value in (source_id, page, document, image)) > 1:
        raise SourceResolutionError(
            "provide at most one of source_id, page, document, or image",
            status_code=422,
            code="invalid_source_filter",
        )

    source: SourceResponse | None
    if source_id is not None:
        source = await get_source(client, source_id)
        resource = "Source"
    elif page is not None:
        library, identifiers = _parse_archive_path(
            page, resource="page", identifier_counts=(1, 2)
        )
        source = await get_source(
            client,
            source_type=SourceKind.page,
            library=library,
            document_id=identifiers[0] if len(identifiers) == 2 else None,
            page_id=identifiers[-1],
        )
        resource = "Page"
    elif document is not None:
        library, identifiers = _parse_archive_path(
            document, resource="document", identifier_counts=(1,)
        )
        source = await get_source(
            client,
            source_type=SourceKind.document,
            library=library,
            document_id=identifiers[0],
        )
        resource = "Document"
    elif image is not None:
        source = await get_source(
            client,
            source_type=SourceKind.image,
            url=image,
        )
        resource = "Image"
    else:
        return None

    if source is None:
        raise SourceResolutionError(
            f"{resource} not found", status_code=404, code="not_found"
        )
    return source.source_id
