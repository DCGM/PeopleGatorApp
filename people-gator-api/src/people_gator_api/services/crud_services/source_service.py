"""Service for source endpoints."""

import logging
import uuid
from collections.abc import Sequence
from urllib.parse import quote

from pydantic import AnyUrl

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    PageSourceMetadata,
    SourceCreateRequest,
    SourceDescriptorRequest,
    SourceListResponse,
    SourceMetadata,
    SourceResponse,
)
from people_gator_api.services.weaviate_service.db_schema import SOURCE_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_source,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


def canonical_page_uri(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> str:
    """Build the stable Digital Library URL for one archive page."""
    encoded_library = quote(library, safe="")
    return (
        f"https://www.digitalniknihovna.cz/{encoded_library}/view/"
        f"uuid:{document_id}?page=uuid:{page_id}"
    )


def canonical_document_uri(
    library: str,
    document_id: uuid.UUID,
) -> str:
    """Build the stable Digital Library URL for one archive document."""
    encoded_library = quote(library, safe="")
    return f"https://www.digitalniknihovna.cz/{encoded_library}/uuid/uuid:{document_id}"


def _canonical_page_metadata(metadata: PageSourceMetadata) -> PageSourceMetadata:
    uri = canonical_page_uri(metadata.library, metadata.document, metadata.page)
    return PageSourceMetadata(
        library=metadata.library,
        document=metadata.document,
        page=metadata.page,
        kramerius_url=AnyUrl(uri),
    )


def _canonical_document_metadata(
    metadata: DocumentSourceMetadata,
) -> DocumentSourceMetadata:
    uri = canonical_document_uri(metadata.library, metadata.document)
    return DocumentSourceMetadata(
        library=metadata.library,
        document=metadata.document,
        kramerius_url=AnyUrl(uri),
    )


class SourceResolutionError(ValueError):
    """Raised when an annotation source reference cannot be resolved."""

    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _source_storage_properties(
    source_type: SourceKind,
    uri: str,
    metadata: SourceMetadata | None,
) -> WeaviateProperties:
    properties: dict[str, WeaviateField] = {
        "source_type": source_type.value,
        "uri": uri,
        "library": None,
        "document": None,
        "page": None,
    }
    if isinstance(metadata, PageSourceMetadata):
        properties.update(
            {
                "library": metadata.library,
                "document": metadata.document,
                "page": metadata.page,
            }
        )
    elif isinstance(metadata, DocumentSourceMetadata):
        properties.update(
            {
                "library": metadata.library,
                "document": metadata.document,
            }
        )
    return properties


def _uri_from_metadata(metadata: SourceMetadata) -> str:
    if isinstance(metadata, PageSourceMetadata):
        return canonical_page_uri(
            metadata.library,
            metadata.document,
            metadata.page,
        )
    return canonical_document_uri(metadata.library, metadata.document)


def _normalize_source(
    payload: SourceCreateRequest,
) -> tuple[SourceKind, str, SourceMetadata | None]:
    """Resolve a validated creation payload into its canonical stored form."""
    metadata = payload.metadata
    if payload.source_type == SourceKind.image:
        if payload.uri is None:  # Protected by SourceCreateRequest validation.
            raise ValueError("image sources require uri")
        return payload.source_type, payload.uri, None
    if metadata is None:  # Protected by SourceCreateRequest validation.
        raise ValueError("page and document sources require metadata")
    if isinstance(metadata, PageSourceMetadata):
        canonical_metadata = _canonical_page_metadata(metadata)
    else:
        canonical_metadata = _canonical_document_metadata(metadata)
    return payload.source_type, _uri_from_metadata(canonical_metadata), canonical_metadata


def _source_request_from_descriptor(
    descriptor: SourceDescriptorRequest,
) -> SourceCreateRequest:
    """Convert one typed annotation descriptor to the common creation contract."""
    if descriptor.page is not None:
        return SourceCreateRequest(
            source_type=SourceKind.page,
            metadata=PageSourceMetadata(
                library=descriptor.page.library,
                document=descriptor.page.document_id,
                page=descriptor.page.page_id,
            ),
        )
    if descriptor.document is not None:
        return SourceCreateRequest(
            source_type=SourceKind.document,
            metadata=DocumentSourceMetadata(
                library=descriptor.document.library,
                document=descriptor.document.document_id,
            ),
        )
    if descriptor.image is not None:
        return SourceCreateRequest(
            source_type=SourceKind.image,
            uri=str(descriptor.image.url),
        )
    raise SourceResolutionError(
        "source descriptor requires page, document, or image",
        status_code=422,
        code="invalid_source_reference",
    )


@trace()
async def resolve_source_reference(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    source: SourceDescriptorRequest | None,
) -> SourceResponse:
    if source_id is not None:
        existing = await get_source(client, source_id)
        if existing is None:
            raise SourceResolutionError(
                "Source not found",
                status_code=404,
                code="not_found",
            )
        return existing

    if source is None:
        raise SourceResolutionError(
            "provide source_id or source",
            status_code=422,
            code="invalid_source_reference",
        )
    resolved, _created = await create_source(
        client,
        _source_request_from_descriptor(source),
    )
    return resolved


@trace()
async def list_sources(
    client: WeaviateAsyncClient,
    source_type: SourceKind | Sequence[SourceKind] | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    uri: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
) -> SourceListResponse:
    logger.debug(
        "list_sources called",
        extra={
            "source_type": (
                source_type.value
                if isinstance(source_type, SourceKind)
                else [item.value for item in source_type]
                if source_type is not None
                else None
            ),
            "after_id": after_id,
            "limit": limit,
            "uri": uri,
            "library": library,
            "document": document,
            "page": page,
        },
    )
    filters: list[FilterReturn] = []
    if isinstance(source_type, SourceKind):
        filters.append(Filter.by_property("source_type").equal(source_type.value))
    elif source_type:
        filters.append(
            Filter.any_of(
                [
                    Filter.by_property("source_type").equal(item.value)
                    for item in source_type
                ]
            )
        )
    if uri is not None:
        filters.append(Filter.by_property("uri").equal(uri))
    if library is not None:
        filters.append(Filter.by_property("library").equal(library))
    if document is not None:
        filters.append(Filter.by_property("document").equal(document))
    if page is not None:
        filters.append(Filter.by_property("page").equal(page))

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        SOURCE_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_source(item.properties, item.references, item.uuid)
            for item in objects
        ],
        key=lambda item: item.source_id,
    )
    return SourceListResponse(
        items=items,
        total_count=total_count,
        after_id=items[-1].source_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def get_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> SourceResponse | None:
    logger.debug("get_source called", extra={"source_id": source_id})
    response = await fetch_collection_object(client, SOURCE_COLLECTION, source_id)
    if response is None:
        logger.info("source not found", extra={"source_id": source_id})
        return None
    logger.debug("source found", extra={"source_id": source_id})
    return parse_source(response.properties, response.references, response.uuid)


@trace()
async def get_source_by_type_uri(
    client: WeaviateAsyncClient,
    source_type: SourceKind,
    uri: str,
) -> SourceResponse | None:
    logger.debug(
        "get_source_by_type_uri called",
        extra={"source_type": source_type.value, "uri": uri},
    )
    source = await _find_source(
        client,
        [
            Filter.by_property("source_type").equal(source_type.value),
            Filter.by_property("uri").equal(uri),
        ],
    )
    if source is None:
        logger.info(
            "source by type and uri not found",
            extra={"source_type": source_type.value, "uri": uri},
        )
        return None
    logger.debug("source by type and uri found", extra={"source_id": source.source_id})
    return source


async def _find_source(
    client: WeaviateAsyncClient,
    filters: Sequence[FilterReturn],
) -> SourceResponse | None:
    """Return the first Source matching an explicit identity filter."""
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=combine_filters(list(filters)),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        return None
    item = response.objects[0]
    return parse_source(item.properties, item.references, item.uuid)


@trace()
async def get_source_by_page_identity(
    client: WeaviateAsyncClient,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> SourceResponse | None:
    return await _find_source(
        client,
        [
            Filter.by_property("source_type").equal(SourceKind.page.value),
            Filter.by_property("library").equal(library),
            Filter.by_property("document").equal(document_id),
            Filter.by_property("page").equal(page_id),
        ],
    )


@trace()
async def get_source_by_page_path(
    client: WeaviateAsyncClient,
    library: str,
    page_id: uuid.UUID,
    *,
    document_id: uuid.UUID | None = None,
) -> SourceResponse | None:
    """Find a page by its canonical archive path components."""
    filters = [
        Filter.by_property("source_type").equal(SourceKind.page.value),
        Filter.by_property("library").equal(library),
        Filter.by_property("page").equal(page_id),
    ]
    if document_id is not None:
        filters.append(Filter.by_property("document").equal(document_id))

    return await _find_source(client, filters)


@trace()
async def get_source_by_document_identity(
    client: WeaviateAsyncClient,
    library: str,
    document_id: uuid.UUID,
) -> SourceResponse | None:
    return await _find_source(
        client,
        [
            Filter.by_property("source_type").equal(SourceKind.document.value),
            Filter.by_property("library").equal(library),
            Filter.by_property("document").equal(document_id),
        ],
    )


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
        identifiers = [uuid.UUID(part) for part in parts[1:]]
    except ValueError as exc:
        raise SourceResolutionError(
            f"invalid {resource} selector; identifiers must be UUIDs",
            status_code=422,
            code="invalid_source_filter",
        ) from exc
    return parts[0], identifiers


@trace()
async def resolve_source_filter(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    page: str | None,
    document: str | None,
    image: str | None,
) -> uuid.UUID | None:
    """Resolve one typed list-filter selector to its internal Source UUID."""
    selectors = [
        source_id is not None,
        page is not None,
        document is not None,
        image is not None,
    ]
    if sum(selectors) > 1:
        raise SourceResolutionError(
            "provide at most one of source_id, page, document, or image",
            status_code=422,
            code="invalid_source_filter",
        )
    if not any(selectors):
        return None

    source: SourceResponse | None
    resource_name: str
    if source_id is not None:
        source = await get_source(client, source_id)
        resource_name = "Source"
    elif page is not None:
        library, identifiers = _parse_archive_path(
            page,
            resource="page",
            identifier_counts=(1, 2),
        )
        if len(identifiers) == 1:
            source = await get_source_by_page_path(
                client,
                library,
                identifiers[0],
            )
        else:
            source = await get_source_by_page_path(
                client,
                library,
                identifiers[1],
                document_id=identifiers[0],
            )
        resource_name = "Page"
    elif document is not None:
        library, identifiers = _parse_archive_path(
            document,
            resource="document",
            identifier_counts=(1,),
        )
        source = await get_source_by_document_identity(
            client,
            library,
            identifiers[0],
        )
        resource_name = "Document"
    else:
        source = await get_source_by_type_uri(
            client,
            SourceKind.image,
            image or "",
        )
        resource_name = "Image"

    if source is None:
        raise SourceResolutionError(
            f"{resource_name} not found",
            status_code=404,
            code="not_found",
        )
    return source.source_id


@trace()
async def create_source(
    client: WeaviateAsyncClient,
    payload: SourceCreateRequest,
) -> tuple[SourceResponse, bool]:
    source_type, uri, metadata = _normalize_source(payload)
    logger.info(
        "create_source called",
        extra={"source_type": source_type.value, "uri": uri},
    )
    if isinstance(metadata, PageSourceMetadata):
        existing = await get_source_by_page_identity(
            client,
            metadata.library,
            metadata.document,
            metadata.page,
        )
    elif isinstance(metadata, DocumentSourceMetadata):
        existing = await get_source_by_document_identity(
            client,
            metadata.library,
            metadata.document,
        )
    else:
        existing = await get_source_by_type_uri(
            client,
            source_type,
            uri,
        )
    if existing is not None:
        logger.info(
            "create_source reused existing source",
            extra={"source_id": existing.source_id},
        )
        return existing, False

    source_id = new_uuid6()
    await client.collections.get(SOURCE_COLLECTION).data.insert(
        uuid=source_id,
        properties=_source_storage_properties(
            source_type,
            uri,
            metadata,
        ),
    )
    return (
        SourceResponse(
            source_id=source_id,
            source_type=source_type,
            uri=uri,
            metadata=metadata,
        ),
        True,
    )


@trace()
async def delete_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> bool:
    logger.info("delete_source called", extra={"source_id": source_id})
    deleted = await client.collections.get(SOURCE_COLLECTION).data.delete_by_id(
        source_id
    )
    logger.info(
        "delete_source completed",
        extra={"source_id": source_id, "deleted": deleted},
    )
    return deleted
