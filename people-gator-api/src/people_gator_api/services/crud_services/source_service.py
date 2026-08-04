"""Service for source endpoints."""

import uuid

from weaviate import (
    WeaviateAsyncClient,
)
from weaviate.classes.query import (
    Filter,
)
from weaviate.collections.classes.filters import (
    FilterReturn,
)

from people_gator_api.schemas.enums import (
    SourceKind,
)
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    SOURCE_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    source_response,
    upsert,
)
from people_gator_api.utils.uuid_utils import (
    new_uuid6,
)


async def list_sources(
    client: WeaviateAsyncClient,
    source_type: SourceKind | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> SourceListResponse:
    filters: list[FilterReturn] = []
    if source_type is not None:
        filters.append(Filter.by_property("source_type").equal(source_type.value))

    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after=after_id,
    )
    items = sorted(
        [source_response(item.properties, item.references, item.uuid) for item in response.objects],
        key=lambda item: item.source_id,
    )
    return SourceListResponse(
        items=items,
        total=len(items),
        next_after_id=items[-1].source_id if len(items) == limit and items else None,
    )


async def get_source(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
) -> SourceResponse | None:
    response = await client.collections.get(SOURCE_COLLECTION).query.fetch_object_by_id(
        source_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return source_response(response.properties, response.references, response.uuid)


async def get_source_by_type_uri(
    client: WeaviateAsyncClient,
    source_type: SourceKind,
    uri: str,
) -> SourceResponse | None:
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
        return None
    item = response.objects[0]
    return source_response(item.properties, item.references, item.uuid)


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


async def delete_source(client: WeaviateAsyncClient, source_id: uuid.UUID) -> bool:
    source = await get_source(client, source_id)
    if source is None:
        return False

    await client.collections.get(SOURCE_COLLECTION).data.delete_by_id(source_id)
    return True
