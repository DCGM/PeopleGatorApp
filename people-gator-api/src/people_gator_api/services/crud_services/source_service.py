"""Service for source endpoints."""

import logging
import uuid
from urllib.parse import urlparse

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    NlcrAuthoritySourceMetadata,
    ObalkyKnihSourceMetadata,
    PageSourceMetadata,
    SourceCreateRequest,
    SourceDescriptorRequest,
    SourceListResponse,
    SourceMetadata,
    SourceResponse,
    WikidataSourceMetadata,
    WikimediaImageSourceMetadata,
)
from people_gator_api.services.weaviate_service.db_schema import SOURCE_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_page_with_total_count,
    source_response,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


class SourceResolutionError(ValueError):
    """Raised when an annotation source reference cannot be resolved."""

    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _source_kind_from_metadata(metadata: SourceMetadata) -> SourceKind:
    if isinstance(metadata, PageSourceMetadata):
        return SourceKind.page
    if isinstance(metadata, DocumentSourceMetadata):
        return SourceKind.document
    if isinstance(metadata, WikidataSourceMetadata):
        return SourceKind.wikidata
    if isinstance(metadata, WikimediaImageSourceMetadata):
        return SourceKind.wikimedia
    if isinstance(metadata, NlcrAuthoritySourceMetadata):
        return SourceKind.nlcr
    return SourceKind.obalkyknih


def _uri_from_metadata(metadata: SourceMetadata) -> str:
    if isinstance(metadata, (PageSourceMetadata, DocumentSourceMetadata)):
        return str(metadata.kramerius_url)
    if isinstance(metadata, WikidataSourceMetadata):
        return str(metadata.wikidata_url)
    if isinstance(metadata, WikimediaImageSourceMetadata):
        return str(metadata.wikimedia_url)
    if isinstance(metadata, ObalkyKnihSourceMetadata):
        return str(metadata.obalkyknih_url)
    return f"nlcr:{metadata.nlcr_id}"


def _infer_source_kind_from_uri(uri: str) -> SourceKind:
    parsed = urlparse(uri)
    host = parsed.netloc.lower()
    if host.endswith("wikidata.org"):
        return SourceKind.wikidata
    if "wikimedia.org" in host:
        return SourceKind.wikimedia
    if "obalkyknih.cz" in host:
        return SourceKind.obalkyknih
    if parsed.scheme == "nlcr":
        return SourceKind.nlcr
    if "kramerius" in host:
        if "page" in parsed.path:
            return SourceKind.page
        return SourceKind.document
    raise SourceResolutionError(
        "could not infer source_type from uri; provide metadata to disambiguate",
        status_code=422,
        code="invalid_source_reference",
    )


@trace()
async def resolve_source_reference(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    *,
    source_id: uuid.UUID | None,
    source: SourceDescriptorRequest | None,
) -> SourceResponse:
    if source_id is not None:
        existing = await get_source(client, principal_id, source_id)
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

    resolved_uri = source.uri
    resolved_metadata = source.metadata
    resolved_kind: SourceKind | None = None
    if resolved_metadata is not None:
        resolved_kind = _source_kind_from_metadata(resolved_metadata)
        if resolved_uri is None:
            resolved_uri = _uri_from_metadata(resolved_metadata)
        else:
            uri_kind = _infer_source_kind_from_uri(resolved_uri)
            if uri_kind != resolved_kind:
                raise SourceResolutionError(
                    "source uri and metadata imply different source types",
                    status_code=422,
                    code="invalid_source_reference",
                )
    if resolved_uri is None:
        raise SourceResolutionError(
            "source descriptor requires uri or metadata",
            status_code=422,
            code="invalid_source_reference",
        )
    if resolved_kind is None:
        resolved_kind = _infer_source_kind_from_uri(resolved_uri)

    existing = await get_source_by_type_uri(
        client,
        principal_id,
        resolved_kind,
        resolved_uri,
    )
    if existing is not None:
        return existing

    new_source_id = new_uuid6()
    await client.collections.get(SOURCE_COLLECTION).data.insert(
        uuid=new_source_id,
        properties={
            "source_type": resolved_kind.value,
            "uri": resolved_uri,
            "metadata": (
                resolved_metadata.model_dump(mode="json")
                if resolved_metadata is not None
                else None
            ),
        },
    )
    return SourceResponse(
        source_id=new_source_id,
        source_type=resolved_kind,
        uri=resolved_uri,
        metadata=resolved_metadata,
    )


@trace()
async def list_sources(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_type: SourceKind | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    uri: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
) -> SourceListResponse:
    del principal_id
    logger.debug(
        "list_sources called",
        extra={
            "source_type": source_type.value if source_type is not None else None,
            "after_id": after_id,
            "limit": limit,
            "uri": uri,
            "library": library,
            "document": document,
            "page": page,
        },
    )
    filters: list[FilterReturn] = []
    if source_type is not None:
        filters.append(Filter.by_property("source_type").equal(source_type.value))
    if uri is not None:
        filters.append(Filter.by_property("uri").equal(uri))
    if library is not None:
        filters.append(Filter.by_property("metadata__library").equal(library))
    if document is not None:
        filters.append(Filter.by_property("metadata__document").equal(str(document)))
    if page is not None:
        filters.append(Filter.by_property("metadata__page").equal(str(page)))

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
            source_response(item.properties, item.references, item.uuid)
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
    principal_id: uuid.UUID,
    source_id: uuid.UUID,
) -> SourceResponse | None:
    del principal_id
    logger.debug("get_source called", extra={"source_id": source_id})
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_object_by_id(
        source_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("source not found", extra={"source_id": source_id})
        return None
    logger.debug("source found", extra={"source_id": source_id})
    return source_response(response.properties, response.references, response.uuid)


@trace()
async def get_source_by_type_uri(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_type: SourceKind,
    uri: str,
) -> SourceResponse | None:
    del principal_id
    logger.debug(
        "get_source_by_type_uri called",
        extra={"source_type": source_type.value, "uri": uri},
    )
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_property("source_type").equal(source_type.value),
                Filter.by_property("uri").equal(uri),
            ]
        ),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        logger.info(
            "source by type and uri not found",
            extra={"source_type": source_type.value, "uri": uri},
        )
        return None
    item = response.objects[0]
    logger.debug("source by type and uri found", extra={"source_id": item.uuid})
    return source_response(item.properties, item.references, item.uuid)


@trace()
async def create_source(
    client: WeaviateAsyncClient,
    payload: SourceCreateRequest,
    principal_id: uuid.UUID,
) -> tuple[SourceResponse, bool]:
    logger.info(
        "create_source called",
        extra={"source_type": payload.source_type.value, "uri": payload.uri},
    )
    existing = await get_source_by_type_uri(
        client,
        principal_id,
        payload.source_type,
        payload.uri,
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
        properties={
            "source_type": payload.source_type.value,
            "uri": payload.uri,
            "metadata": payload.metadata.model_dump(mode="json"),
        },
    )
    return (
        SourceResponse(
            source_id=source_id,
            source_type=payload.source_type,
            uri=payload.uri,
            metadata=payload.metadata,
        ),
        True,
    )


@trace()
async def delete_source(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_id: uuid.UUID,
) -> bool:
    logger.info("delete_source called", extra={"source_id": source_id})
    source = await get_source(client, principal_id, source_id)
    if source is None:
        logger.info(
            "delete_source skipped missing source", extra={"source_id": source_id}
        )
        return False

    await client.collections.get(SOURCE_COLLECTION).data.delete_by_id(source_id)
    logger.info("delete_source completed", extra={"source_id": source_id})
    return True
