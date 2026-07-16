"""Service for source endpoints."""

import json
import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import SourceCreateRequest
from people_gator_api.schemas.sources import SourceListResponse
from people_gator_api.schemas.sources import SourceResponse
from people_gator_api.services.vector_service.schema import SOURCE_COLLECTION
from people_gator_api.services.weaviate_utils import combine_filters
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import fetch_single
from people_gator_api.services.weaviate_utils import source_response
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


async def list_sources(
    client: WeaviateAsyncClient,
    source_type: SourceKind | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> SourceListResponse:
    scan_limit = max(limit * 10, 1000)
    filters: list[object] = []
    if source_type is not None:
        filters.append(Filter.by_property("source_type").equal(source_type.value))

    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    items = sorted(
        [source_response(item.properties) for item in response.objects],
        key=lambda item: item.source_id,
    )
    if after_id is not None:
        items = [item for item in items if item.source_id > after_id]
    page_items = items[:limit]
    return SourceListResponse(
        items=page_items,
        total=len(page_items),
        next_after_id=page_items[-1].source_id if len(page_items) == limit and page_items else None,
    )


async def get_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> SourceResponse | None:
    obj = await fetch_by_id(client, SOURCE_COLLECTION, "source_id", source_id)
    if obj is None:
        return None
    return source_response(obj.properties)


async def get_source_by_type_uri(
    client: WeaviateAsyncClient,
    source_type: SourceKind,
    uri: str,
) -> SourceResponse | None:
    obj = await fetch_single(
        client,
        SOURCE_COLLECTION,
        Filter.all_of(
            [
                Filter.by_property("source_type").equal(source_type.value),
                Filter.by_property("uri").equal(uri),
            ]
        ),
    )
    if obj is None:
        return None
    return source_response(obj.properties)


async def create_source(
    client: WeaviateAsyncClient,
    payload: SourceCreateRequest,
    _created_by: uuid.UUID | None,
) -> tuple[SourceResponse, bool]:
    existing = await get_source_by_type_uri(client, payload.source_type, payload.uri)
    if existing is not None:
        return existing, False

    source_id = new_uuid6()
    await upsert(
        client,
        SOURCE_COLLECTION,
        source_id,
        properties={
            "source_id": source_id,
            "source_type": payload.source_type.value,
            "uri": payload.uri,
            "metadata": json.dumps(payload.metadata) if payload.metadata is not None else None,
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
