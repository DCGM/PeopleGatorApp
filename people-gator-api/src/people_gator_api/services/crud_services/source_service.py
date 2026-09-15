"""Service for source endpoints."""

import logging
import uuid
from collections.abc import Sequence
from urllib.parse import quote, urlparse

from pydantic import AnyUrl

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties

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
        "metadata": metadata.model_dump(mode="json") if metadata is not None else None,
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
    if isinstance(metadata, PageSourceMetadata):
        return canonical_page_uri(
            metadata.library,
            metadata.document,
            metadata.page,
        )
    if isinstance(metadata, DocumentSourceMetadata):
        return canonical_document_uri(metadata.library, metadata.document)
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
    if source.page is not None:
        resolved_uri = canonical_page_uri(
            source.page.library,
            source.page.document_id,
            source.page.page_id,
        )
        resolved_kind = SourceKind.page
        resolved_metadata = PageSourceMetadata(
            library=source.page.library,
            document=source.page.document_id,
            page=source.page.page_id,
            kramerius_url=AnyUrl(resolved_uri),
        )
    elif source.document is not None:
        resolved_uri = canonical_document_uri(
            source.document.library,
            source.document.document_id,
        )
        resolved_kind = SourceKind.document
        resolved_metadata = DocumentSourceMetadata(
            library=source.document.library,
            document=source.document.document_id,
            kramerius_url=AnyUrl(resolved_uri),
        )
    elif source.image is not None:
        resolved_uri = str(source.image.url)
        resolved_kind = SourceKind.image
        resolved_metadata = None
    elif resolved_metadata is not None:
        resolved_kind = _source_kind_from_metadata(resolved_metadata)
        resolved_uri = _uri_from_metadata(resolved_metadata)
        if isinstance(resolved_metadata, PageSourceMetadata):
            resolved_metadata = _canonical_page_metadata(resolved_metadata)
        elif isinstance(resolved_metadata, DocumentSourceMetadata):
            resolved_metadata = _canonical_document_metadata(resolved_metadata)
    if resolved_uri is None:
        raise SourceResolutionError(
            "source descriptor requires uri or metadata",
            status_code=422,
            code="invalid_source_reference",
        )
    if resolved_kind is None:
        resolved_kind = _infer_source_kind_from_uri(resolved_uri)

    if isinstance(resolved_metadata, PageSourceMetadata):
        existing = await get_source_by_page_identity(
            client,
            principal_id,
            resolved_metadata.library,
            resolved_metadata.document,
            resolved_metadata.page,
        )
    elif isinstance(resolved_metadata, DocumentSourceMetadata):
        existing = await get_source_by_document_identity(
            client,
            principal_id,
            resolved_metadata.library,
            resolved_metadata.document,
        )
    else:
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
        properties=_source_storage_properties(
            resolved_kind,
            resolved_uri,
            resolved_metadata,
        ),
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
    source_type: SourceKind | Sequence[SourceKind] | None,
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
async def get_source_by_page_identity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> SourceResponse | None:
    del principal_id
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_property("source_type").equal(SourceKind.page.value),
                Filter.by_property("library").equal(library),
                Filter.by_property("document").equal(document_id),
                Filter.by_property("page").equal(page_id),
            ]
        ),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        return None
    item = response.objects[0]
    return source_response(item.properties, item.references, item.uuid)


@trace()
async def get_source_by_page_path(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    library: str,
    page_id: uuid.UUID,
    *,
    document_id: uuid.UUID | None = None,
) -> SourceResponse | None:
    """Find a page by its canonical archive path components."""
    del principal_id
    filters = [
        Filter.by_property("source_type").equal(SourceKind.page.value),
        Filter.by_property("library").equal(library),
        Filter.by_property("page").equal(page_id),
    ]
    if document_id is not None:
        filters.append(Filter.by_property("document").equal(document_id))

    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=Filter.all_of(filters),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        return None
    item = response.objects[0]
    return source_response(item.properties, item.references, item.uuid)


@trace()
async def get_source_by_document_identity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    library: str,
    document_id: uuid.UUID,
) -> SourceResponse | None:
    del principal_id
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_property("source_type").equal(SourceKind.document.value),
                Filter.by_property("library").equal(library),
                Filter.by_property("document").equal(document_id),
            ]
        ),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        return None
    item = response.objects[0]
    return source_response(item.properties, item.references, item.uuid)


@trace()
async def get_source_by_types_uri(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_types: Sequence[SourceKind],
    uri: str,
) -> SourceResponse | None:
    del principal_id
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.any_of(
                    [
                        Filter.by_property("source_type").equal(source_type.value)
                        for source_type in source_types
                    ]
                ),
                Filter.by_property("uri").equal(uri),
            ]
        ),
        limit=1,
        return_references=empty_reference_queries([]),
    )
    if not response.objects:
        return None
    item = response.objects[0]
    return source_response(item.properties, item.references, item.uuid)


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
    principal_id: uuid.UUID,
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
        source = await get_source(client, principal_id, source_id)
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
                principal_id,
                library,
                identifiers[0],
            )
        else:
            source = await get_source_by_page_path(
                client,
                principal_id,
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
            principal_id,
            library,
            identifiers[0],
        )
        resource_name = "Document"
    else:
        source = await get_source_by_types_uri(
            client,
            principal_id,
            (SourceKind.image, SourceKind.wikimedia, SourceKind.obalkyknih),
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
    principal_id: uuid.UUID,
) -> tuple[SourceResponse, bool]:
    metadata = payload.metadata
    if payload.source_type == SourceKind.image:
        if payload.uri is None:
            raise ValueError("image sources require uri")
        uri = payload.uri
    else:
        if metadata is None:
            raise ValueError("metadata-backed sources require metadata")
        uri = _uri_from_metadata(metadata)
        if isinstance(metadata, PageSourceMetadata):
            metadata = _canonical_page_metadata(metadata)
        elif isinstance(metadata, DocumentSourceMetadata):
            metadata = _canonical_document_metadata(metadata)
    logger.info(
        "create_source called",
        extra={"source_type": payload.source_type.value, "uri": uri},
    )
    if isinstance(metadata, PageSourceMetadata):
        existing = await get_source_by_page_identity(
            client,
            principal_id,
            metadata.library,
            metadata.document,
            metadata.page,
        )
    elif isinstance(metadata, DocumentSourceMetadata):
        existing = await get_source_by_document_identity(
            client,
            principal_id,
            metadata.library,
            metadata.document,
        )
    else:
        existing = await get_source_by_type_uri(
            client,
            principal_id,
            payload.source_type,
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
            payload.source_type,
            uri,
            metadata,
        ),
    )
    return (
        SourceResponse(
            source_id=source_id,
            source_type=payload.source_type,
            uri=uri,
            metadata=metadata,
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
