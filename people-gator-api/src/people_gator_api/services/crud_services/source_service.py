"""Service for source endpoints."""

import logging
import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    SourceCreateRequest,
    SourceListResponse,
    SourceResponse,
)
from people_gator_api.services.weaviate_service.db_schema import SOURCE_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_page_with_total_count,
    source_response,
    upsert,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


@trace()
async def list_sources(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_type: SourceKind | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> SourceListResponse:
    del principal_id
    logger.debug(
        "list_sources called",
        extra={
            "source_type": source_type.value if source_type is not None else None,
            "after_id": after_id,
            "limit": limit,
        },
    )
    filters: list[FilterReturn] = []
    if source_type is not None:
        filters.append(Filter.by_property("source_type").equal(source_type.value))

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
