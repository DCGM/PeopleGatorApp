"""Typed page, document, and image projections over the internal Source graph."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, cast

from pydantic import AnyUrl
from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentSourceMetadata,
    ImageCreateRequest,
    ImageListResponse,
    ImageResponse,
    PageSourceMetadata,
    PageCreateRequest,
    PageListResponse,
    PageResponse,
    SourceCreateRequest,
    SourceResponse,
)
from people_gator_api.services.crud_services.source_service import (
    canonical_document_uri,
    canonical_page_uri,
    create_source,
    get_source,
    get_source_by_document_identity,
    get_source_by_page_path,
    get_source_by_page_identity,
    get_source_by_type_uri,
    get_source_by_types_uri,
    list_sources,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DOCUMENT_MENTION_COLLECTION,
    FACE_COLLECTION,
    PAGE_MENTION_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    empty_reference_queries,
    reference_id_filter,
    require_reference_uuid,
)
from people_gator_api.utils.opentelemetry import trace


IMAGE_SOURCE_KINDS: tuple[SourceKind, ...] = (SourceKind.image,)
_RELATION_PAGE_SIZE = 100


class _ReferencedObject(Protocol):
    uuid: uuid.UUID
    properties: WeaviateProperties
    references: CrossReferences


def page_response(source: SourceResponse) -> PageResponse:
    """Map a page Source to its public page representation."""
    if source.source_type != SourceKind.page or not isinstance(
        source.metadata, PageSourceMetadata
    ):
        raise ValueError("Source is not a page")
    return PageResponse(
        page_source_id=source.source_id,
        library=source.metadata.library,
        document_id=source.metadata.document,
        page_id=source.metadata.page,
        url=AnyUrl(
            canonical_page_uri(
                source.metadata.library,
                source.metadata.document,
                source.metadata.page,
            )
        ),
    )


def document_response(source: SourceResponse) -> DocumentResponse:
    """Map a document Source to its public document representation."""
    if source.source_type != SourceKind.document or not isinstance(
        source.metadata, DocumentSourceMetadata
    ):
        raise ValueError("Source is not a document")
    return DocumentResponse(
        document_source_id=source.source_id,
        library=source.metadata.library,
        document_id=source.metadata.document,
        url=AnyUrl(
            canonical_document_uri(
                source.metadata.library,
                source.metadata.document,
            )
        ),
    )


def image_response(source: SourceResponse) -> ImageResponse:
    """Map an image-compatible Source to its public image representation."""
    if source.source_type not in IMAGE_SOURCE_KINDS:
        raise ValueError("Source is not an image")
    return ImageResponse(image_id=source.source_id, url=AnyUrl(source.uri))


@trace()
async def create_page(
    client: WeaviateAsyncClient,
    payload: PageCreateRequest,
    principal_id: uuid.UUID,
) -> tuple[PageResponse, bool]:
    existing = await get_source_by_page_identity(
        client,
        payload.library,
        payload.document_id,
        payload.page_id,
    )
    if existing is not None:
        return page_response(existing), False
    uri = canonical_page_uri(
        payload.library,
        payload.document_id,
        payload.page_id,
    )
    source, created = await create_source(
        client,
        SourceCreateRequest(
            source_type=SourceKind.page,
            metadata=PageSourceMetadata(
                library=payload.library,
                document=payload.document_id,
                page=payload.page_id,
                kramerius_url=AnyUrl(uri),
            ),
        ),
        principal_id,
    )
    return page_response(source), created


@trace()
async def create_document(
    client: WeaviateAsyncClient,
    payload: DocumentCreateRequest,
    principal_id: uuid.UUID,
) -> tuple[DocumentResponse, bool]:
    existing = await get_source_by_document_identity(
        client,
        payload.library,
        payload.document_id,
    )
    if existing is not None:
        return document_response(existing), False
    uri = canonical_document_uri(payload.library, payload.document_id)
    source, created = await create_source(
        client,
        SourceCreateRequest(
            source_type=SourceKind.document,
            metadata=DocumentSourceMetadata(
                library=payload.library,
                document=payload.document_id,
                kramerius_url=AnyUrl(uri),
            ),
        ),
        principal_id,
    )
    return document_response(source), created


@trace()
async def create_image(
    client: WeaviateAsyncClient,
    payload: ImageCreateRequest,
    principal_id: uuid.UUID,
) -> tuple[ImageResponse, bool]:
    source, created = await create_source(
        client,
        SourceCreateRequest(
            source_type=SourceKind.image,
            uri=str(payload.url),
            metadata=None,
        ),
        principal_id,
    )
    return image_response(source), created


@trace()
async def list_pages(
    client: WeaviateAsyncClient,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
) -> PageListResponse:
    sources = await list_sources(
        client,
        SourceKind.page,
        after_id,
        limit,
        library=library,
        document=document_id,
        page=page_id,
    )
    return PageListResponse(
        items=[page_response(source) for source in sources.items],
        total_count=sources.total_count,
        limit=sources.limit,
        after_id=sources.after_id,
    )


@trace()
async def list_documents(
    client: WeaviateAsyncClient,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
) -> DocumentListResponse:
    sources = await list_sources(
        client,        SourceKind.document,
        after_id,
        limit,
        library=library,
        document=document_id,
    )
    return DocumentListResponse(
        items=[document_response(source) for source in sources.items],
        total_count=sources.total_count,
        limit=sources.limit,
        after_id=sources.after_id,
    )


@trace()
async def list_images(
    client: WeaviateAsyncClient,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    url: str | None = None,
) -> ImageListResponse:
    sources = await list_sources(
        client,
        IMAGE_SOURCE_KINDS,
        after_id,
        limit,
        uri=url,
    )
    return ImageListResponse(
        items=[image_response(source) for source in sources.items],
        total_count=sources.total_count,
        limit=sources.limit,
        after_id=sources.after_id,
    )


@trace()
async def get_page(
    client: WeaviateAsyncClient,
    page_source_id: uuid.UUID,
) -> PageResponse | None:
    source = await get_source(client, page_source_id)
    if source is None or source.source_type != SourceKind.page:
        return None
    return page_response(source)


@trace()
async def get_page_by_path(
    client: WeaviateAsyncClient,
    library: str,
    page_id: uuid.UUID,
    *,
    document_id: uuid.UUID | None = None,
) -> PageResponse | None:
    source = await get_source_by_page_path(
        client,
        library,
        page_id,
        document_id=document_id,
    )
    return page_response(source) if source is not None else None


@trace()
async def get_page_by_url(
    client: WeaviateAsyncClient,
    url: str,
) -> PageResponse | None:
    source = await get_source_by_type_uri(
        client,
        SourceKind.page,
        url,
    )
    return page_response(source) if source is not None else None


@trace()
async def get_document_by_path(
    client: WeaviateAsyncClient,
    library: str,
    document_id: uuid.UUID,
) -> DocumentResponse | None:
    source = await get_source_by_document_identity(
        client,
        library,
        document_id,
    )
    return document_response(source) if source is not None else None


@trace()
async def get_document(
    client: WeaviateAsyncClient,
    document_source_id: uuid.UUID,
) -> DocumentResponse | None:
    source = await get_source(client, document_source_id)
    if source is None or source.source_type != SourceKind.document:
        return None
    return document_response(source)


@trace()
async def get_document_by_url(
    client: WeaviateAsyncClient,
    url: str,
) -> DocumentResponse | None:
    source = await get_source_by_type_uri(
        client,
        SourceKind.document,
        url,
    )
    return document_response(source) if source is not None else None


@trace()
async def get_image(
    client: WeaviateAsyncClient,
    image_id: uuid.UUID,
) -> ImageResponse | None:
    source = await get_source(client, image_id)
    if source is None or source.source_type not in IMAGE_SOURCE_KINDS:
        return None
    return image_response(source)


@trace()
async def get_image_by_url(
    client: WeaviateAsyncClient,
    url: str,
) -> ImageResponse | None:
    source = await get_source_by_types_uri(
        client,
        IMAGE_SOURCE_KINDS,
        url,
    )
    return image_response(source) if source is not None else None


async def _fetch_all_references(
    client: WeaviateAsyncClient,
    collection_name: str,
    *,
    filters: FilterReturn,
    reference_names: Sequence[str],
) -> list[_ReferencedObject]:
    collection = client.collections.get(collection_name)
    objects: list[_ReferencedObject] = []
    after_id: uuid.UUID | None = None
    while True:
        response = await collection.query.fetch_objects(
            limit=_RELATION_PAGE_SIZE,
            after=after_id,
            filters=filters,
            return_properties=[],
            return_references=empty_reference_queries(reference_names),
        )
        page = cast(list[_ReferencedObject], list(response.objects))
        if not page:
            break
        objects.extend(page)
        if len(page) < _RELATION_PAGE_SIZE:
            break
        next_after_id = page[-1].uuid
        if next_after_id == after_id:
            raise RuntimeError("Weaviate relation pagination did not advance")
        after_id = next_after_id
    return objects


def _reference_ids(
    objects: Sequence[_ReferencedObject], reference_name: str
) -> set[uuid.UUID]:
    ids: set[uuid.UUID] = set()
    for item in objects:
        try:
            ids.add(require_reference_uuid(item.references, reference_name))
        except KeyError:
            continue
    return ids


@trace()
async def entity_ids_for_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> set[uuid.UUID]:
    """Collect entities connected to a Source through any annotation type."""
    source_filter = reference_id_filter(link_on="source", reference_id=source_id)
    faces = await _fetch_all_references(
        client,
        FACE_COLLECTION,
        filters=source_filter,
        reference_names=["entity"],
    )
    document_mentions = await _fetch_all_references(
        client,
        DOCUMENT_MENTION_COLLECTION,
        filters=source_filter,
        reference_names=["entity"],
    )
    page_mentions = await _fetch_all_references(
        client,
        PAGE_MENTION_COLLECTION,
        filters=source_filter,
        reference_names=["document_mention"],
    )

    document_mention_ids = _reference_ids(page_mentions, "document_mention")
    if document_mention_ids:
        referenced_documents = await client.collections.get(
            DOCUMENT_MENTION_COLLECTION
        ).query.fetch_objects_by_ids(
            list(document_mention_ids),
            return_properties=[],
            return_references=empty_reference_queries(["entity"]),
        )
        document_mentions.extend(referenced_documents.objects)

    return _reference_ids(faces, "entity") | _reference_ids(document_mentions, "entity")
