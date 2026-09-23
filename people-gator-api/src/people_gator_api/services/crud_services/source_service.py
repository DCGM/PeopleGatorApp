"""CRUD operations for sources."""

import uuid
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from urllib.parse import parse_qsl, quote, urlparse, urlencode

from pydantic import AnyUrl
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    PageSourceMetadata,
    SourceRecordListResponse,
    SourceMetadata,
    SourceRecord,
)
from people_gator_api.weaviate_schema import SOURCE_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_source,
)
from people_gator_api.utils.opentelemetry import trace


type SourceIdentityKey = tuple[SourceKind, str, uuid.UUID | None, uuid.UUID | None]
_SOURCE_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "http://peoplegator/source")


@dataclass(frozen=True, slots=True)
class SourceCreateSpec:
    """Complete typed identity for one source requested by a batch import."""

    source_type: SourceKind
    library: str | None = None
    document_id: uuid.UUID | None = None
    page_id: uuid.UUID | None = None
    url: str | None = None


def _spec_identity(spec: SourceCreateSpec) -> SourceIdentityKey:
    return (
        spec.source_type,
        canonical_source_uri(spec.url) if spec.url is not None else spec.library or "",
        spec.document_id,
        spec.page_id,
    )


def _record_identity(source: SourceRecord) -> SourceIdentityKey:
    if isinstance(source.metadata, PageSourceMetadata):
        return (
            source.source_type,
            source.metadata.library,
            source.metadata.document,
            source.metadata.page,
        )
    if isinstance(source.metadata, DocumentSourceMetadata):
        return (
            source.source_type,
            source.metadata.library,
            source.metadata.document,
            None,
        )
    return (source.source_type, canonical_source_uri(source.uri), None, None)


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


def canonical_source_uri(uri: str) -> str:
    parsed_uri = urlparse(uri)
    query_dict = sorted(parse_qsl(parsed_uri.query))
    normalized_query = urlencode(query_dict)
    normalized_uri = parsed_uri._replace(query=normalized_query).geturl()
    return normalized_uri


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
        raise ValueError("page sources require only library, document_id, and page_id")
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


def _source_uri(
    source_type: SourceKind,
    *,
    library: str | None,
    document_id: uuid.UUID | None,
    page_id: uuid.UUID | None,
    url: str | None,
) -> str:
    """Return the canonical, hashable database identity for one source."""
    if source_type == SourceKind.image and url is not None:
        return canonical_source_uri(url)
    if (
        source_type == SourceKind.page
        and library is not None
        and document_id is not None
        and page_id is not None
    ):
        return canonical_source_uri(canonical_page_uri(library, document_id, page_id))
    if (
        source_type == SourceKind.document
        and library is not None
        and document_id is not None
    ):
        return canonical_source_uri(canonical_document_uri(library, document_id))
    raise ValueError("document sources require library and document_id")


def _source_uuid(
    source_type: SourceKind,
    *,
    library: str | None,
    document_id: uuid.UUID | None,
    page_id: uuid.UUID | None,
    url: str | None,
) -> uuid.UUID:
    """Generate the stable Weaviate ID that enforces identity under races."""
    source_uri = _source_uri(
        source_type, library=library, document_id=document_id, page_id=page_id, url=url
    )
    return uuid.uuid5(_SOURCE_ID_NAMESPACE, f"{source_type.value}:{source_uri}")


def source_content(
    source_type: SourceKind,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    url: str | None = None,
) -> tuple[str, SourceMetadata | None]:
    """Public backend-neutral source validation and canonicalization helper."""
    return _source_content(
        source_type,
        library=library,
        document_id=document_id,
        page_id=page_id,
        url=url,
    )


def stable_source_uuid(
    source_type: SourceKind,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    url: str | None = None,
) -> uuid.UUID:
    """Return the shared deterministic source ID used by every backend."""
    return _source_uuid(
        source_type,
        library=library,
        document_id=document_id,
        page_id=page_id,
        url=url,
    )


async def _first_source(
    client: WeaviateAsyncClient,
    filters: Sequence[FilterReturn],
) -> SourceRecord | None:
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
) -> tuple[SourceRecord, bool]:
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
    source_uuid = _source_uuid(
        source_type, library=library, document_id=document_id, page_id=page_id, url=url
    )
    source = SourceRecord(
        source_id=source_uuid,
        source_type=source_type,
        uri=uri,
        metadata=metadata,
    )
    try:
        await client.collections.get(SOURCE_COLLECTION).data.insert(
            uuid=source.source_id,
            properties=_storage_properties(source_type, uri, metadata),
        )
    except Exception:
        # A concurrent importer can win after the identity lookup. Stable IDs
        # turn that race into a duplicate-ID error instead of a duplicate row.
        raced_source = await get_source(
            client,
            source_type=source_type,
            library=library,
            document_id=document_id,
            page_id=page_id,
            url=url,
        )
        if raced_source is not None and raced_source.source_id == source_uuid:
            return raced_source, False
        raise
    return source, True


@trace()
async def create_source_batch(
    client: WeaviateAsyncClient,
    specs: Sequence[SourceCreateSpec],
) -> list[SourceRecord]:
    """Resolve or create sources in one preflight query and one write batch.

    Repeated identities in ``specs`` are queried and inserted only once, but
    their resolved record is repeated at the corresponding response positions.
    """
    if not specs:
        return []
    collection = client.collections.use(SOURCE_COLLECTION)
    source_uuids = [
        _source_uuid(
            spec.source_type,
            library=spec.library,
            document_id=spec.document_id,
            page_id=spec.page_id,
            url=spec.url,
        )
        for spec in specs
    ]
    response = await collection.query.fetch_objects(
        filters=Filter.by_id().contains_any(source_uuids),
        limit=len(set(source_uuids)),
        return_references=empty_reference_queries([]),
    )
    resolved_by_uuid: dict[uuid.UUID, SourceRecord] = {}
    requested_uuid_by_identity = {
        _spec_identity(spec): source_uuid
        for source_uuid, spec in zip(source_uuids, specs)
    }
    for item in response.objects:
        source = parse_source(item.properties, item.references, item.uuid)
        requested_uuid = requested_uuid_by_identity.get(_record_identity(source))
        if requested_uuid is not None:
            # Keep the first record if legacy data already contains a duplicate.
            resolved_by_uuid.setdefault(requested_uuid, source)
    missing_by_uuid: dict[uuid.UUID, SourceCreateSpec] = {}
    for source_uuid, spec in zip(source_uuids, specs):
        if source_uuid not in resolved_by_uuid:
            missing_by_uuid.setdefault(source_uuid, spec)
    missing = list(missing_by_uuid.items())
    async with collection.batch.stream() as batch:
        for source_uuid, spec in missing:
            source_uri, source_metadata = _source_content(
                spec.source_type,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
                url=spec.url,
            )
            await batch.add_object(
                uuid=source_uuid,
                properties=_storage_properties(
                    spec.source_type, source_uri, source_metadata
                ),
            )
            resolved_by_uuid[source_uuid] = SourceRecord(
                source_id=source_uuid,
                source_type=spec.source_type,
                uri=source_uri,
                metadata=source_metadata,
            )
    failed_objects = collection.batch.failed_objects
    if failed_objects:
        failed_ids = {
            failed.object_.uuid
            for failed in failed_objects
            if failed.object_.uuid is not None
        }
        verified = await collection.query.fetch_objects_by_ids(
            failed_ids,
            return_references=empty_reference_queries([]),
        )
        verified_ids = {item.uuid for item in verified.objects}
        unresolved_ids = failed_ids - verified_ids
        if unresolved_ids:
            messages = "; ".join(
                failed.message
                for failed in failed_objects
                if failed.object_.uuid in unresolved_ids
            )
            raise RuntimeError(f"Source batch import failed: {messages}")
    return [resolved_by_uuid[key] for key in source_uuids]


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
) -> SourceRecord | None:
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
    source_ids: Collection[uuid.UUID] | None = None,
) -> SourceRecordListResponse:
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
    if source_ids is not None:
        if not source_ids:
            return SourceRecordListResponse(
                items=[], total_count=0, limit=limit, after_id=None
            )
        filters.append(Filter.by_id().contains_any(sorted(source_ids)))
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
    return SourceRecordListResponse(
        items=items,
        total_count=total_count,
        after_id=items[-1].source_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def delete_source(client: WeaviateAsyncClient, source_id: uuid.UUID) -> bool:
    return await client.collections.get(SOURCE_COLLECTION).data.delete_by_id(source_id)
