"""CRUD operations for sources."""

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


def canonical_page_uri(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> str:
    library = quote(library, safe="")
    return (
        f"https://www.digitalniknihovna.cz/{library}/view/"
        f"uuid:{document_id}?page=uuid:{page_id}"
    )


def canonical_document_uri(library: str, document_id: uuid.UUID) -> str:
    library = quote(library, safe="")
    return f"https://www.digitalniknihovna.cz/{library}/uuid/uuid:{document_id}"


class SourceResolutionError(ValueError):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _source_content(
    source_type: SourceKind,
    *,
    library: str | None,
    document_id: uuid.UUID | None,
    page_id: uuid.UUID | None,
    url: str | None,
) -> tuple[str, SourceMetadata | None]:
    """Validate and normalize the complete content needed to create a source."""
    if source_type == SourceKind.image:
        if url is None or any(
            value is not None for value in (library, document_id, page_id)
        ):
            raise ValueError("image sources require only url")
        return url, None

    if source_type == SourceKind.document:
        if (
            library is None
            or document_id is None
            or page_id is not None
            or url is not None
        ):
            raise ValueError("document sources require only library and document_id")
        return (
            canonical_document_uri(library, document_id),
            DocumentSourceMetadata(library=library, document=document_id),
        )

    if library is None or document_id is None or page_id is None or url is not None:
        raise ValueError(
            "page sources require only library, document_id, and page_id"
        )
    uri = canonical_page_uri(library, document_id, page_id)
    return (
        uri,
        PageSourceMetadata(
            library=library,
            document=document_id,
            page=page_id,
            kramerius_url=AnyUrl(uri),
        ),
    )


def _identity_filters(
    source_type: SourceKind,
    *,
    library: str | None,
    document_id: uuid.UUID | None,
    page_id: uuid.UUID | None,
    url: str | None,
) -> list[FilterReturn]:
    """Validate one typed lookup identity and return its filters."""
    filters = [Filter.by_property("source_type").equal(source_type.value)]
    if url is not None:
        if any(value is not None for value in (library, document_id, page_id)):
            raise ValueError("url cannot be combined with archive identity fields")
        return [*filters, Filter.by_property("uri").equal(url)]

    if source_type == SourceKind.image:
        raise ValueError("image sources require url")
    if library is None:
        raise ValueError(f"{source_type.value} sources require library")
    if source_type == SourceKind.document:
        if document_id is None or page_id is not None:
            raise ValueError("document sources require document_id and no page_id")
    elif page_id is None:
        raise ValueError("page sources require page_id")

    filters.append(Filter.by_property("library").equal(library))
    if document_id is not None:
        filters.append(Filter.by_property("document").equal(document_id))
    if page_id is not None:
        filters.append(Filter.by_property("page").equal(page_id))
    return filters


def _storage_properties(
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
    if isinstance(metadata, (PageSourceMetadata, DocumentSourceMetadata)):
        properties["library"] = metadata.library
        properties["document"] = metadata.document
    if isinstance(metadata, PageSourceMetadata):
        properties["page"] = metadata.page
    return properties


async def _first_source(
    client: WeaviateAsyncClient,
    filters: Sequence[FilterReturn],
) -> SourceResponse | None:
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
async def create_source(
    client: WeaviateAsyncClient,
    source_type: SourceKind,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    url: str | None = None,
) -> tuple[SourceResponse, bool]:
    """Create a source, or return the existing source with the same identity."""
    uri, metadata = _source_content(
        source_type,
        library=library,
        document_id=document_id,
        page_id=page_id,
        url=url,
    )
    existing = await get_source(
        client,
        source_type=source_type,
        library=library,
        document_id=document_id,
        page_id=page_id,
        url=url,
    )
    if existing is not None:
        return existing, False

    source = SourceResponse(
        source_id=new_uuid6(),
        source_type=source_type,
        uri=uri,
        metadata=metadata,
    )
    await client.collections.get(SOURCE_COLLECTION).data.insert(
        uuid=source.source_id,
        properties=_storage_properties(source_type, uri, metadata),
    )
    return source, True


@trace()
async def get_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None = None,
    *,
    source_type: SourceKind | None = None,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    url: str | None = None,
) -> SourceResponse | None:
    """Get a source by UUID, URL, or one complete typed identity."""
    has_identity = any(
        value is not None for value in (source_type, library, document_id, page_id, url)
    )
    if source_id is not None:
        if has_identity:
            raise ValueError("source_id cannot be combined with another selector")
        response = await fetch_collection_object(client, SOURCE_COLLECTION, source_id)
        if response is None:
            return None
        return parse_source(response.properties, response.references, response.uuid)

    if source_type is None:
        if url is None or any(
            value is not None for value in (library, document_id, page_id)
        ):
            raise ValueError("provide source_id, url, or source_type with its identity")
        return await _first_source(
            client,
            [Filter.by_property("uri").equal(url)],
        )
    return await _first_source(
        client,
        _identity_filters(
            source_type,
            library=library,
            document_id=document_id,
            page_id=page_id,
            url=url,
        ),
    )


@trace()
async def list_sources(
    client: WeaviateAsyncClient,
    source_type: SourceKind | None = None,
    after_id: uuid.UUID | None = None,
    limit: int = 50,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    url: str | None = None,
) -> SourceListResponse:
    """List sources, optionally filtered by type and stored identity fields."""
    values = {
        "source_type": source_type.value if source_type is not None else None,
        "library": library,
        "document": document_id,
        "page": page_id,
        "uri": url,
    }
    filters = [
        Filter.by_property(name).equal(value)
        for name, value in values.items()
        if value is not None
    ]
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        SOURCE_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        (parse_source(item.properties, item.references, item.uuid) for item in objects),
        key=lambda item: item.source_id,
    )
    return SourceListResponse(
        items=items,
        total_count=total_count,
        after_id=items[-1].source_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def delete_source(client: WeaviateAsyncClient, source_id: uuid.UUID) -> bool:
    return await client.collections.get(SOURCE_COLLECTION).data.delete_by_id(source_id)
