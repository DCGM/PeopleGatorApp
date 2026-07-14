"""Service for source endpoints."""

import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.classes.query import Sort

from people_gator_api.models.enums import SourceKind
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
    filters: list[object] = []
    if source_type is not None:
        filters.append(Filter.by_property("source_type").equal(source_type.value))
    if after_id is not None:
        filters.append(Filter.by_property("source_id").greater_than(str(after_id)))

    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        sort=Sort.by_property("source_id", ascending=True),
        limit=limit,
    )
    items = [source_response(item.properties) for item in response.objects]
    return SourceListResponse(
        items=items,
        total=len(items),
        next_after_id=items[-1].source_id if len(items) == limit and items else None,
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
            "metadata": payload.metadata,
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
