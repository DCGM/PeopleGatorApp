"""Service for entity endpoints."""

import logging
import uuid
from typing import TypeGuard

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DEFAULT_FULLTEXT_VECTOR,
    DEFAULT_NAME_VECTOR,
    ENTITY_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    entity_response,
    fetch_collection_page_with_total_count,
    require_reference_uuid,
    upsert,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


def _is_flat_float_vector(
    value: list[float] | list[list[float]],
) -> TypeGuard[list[float]]:
    return all(isinstance(item, (int, float)) for item in value)


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@trace()
async def list_entities(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    after_id: uuid.UUID | None,
    limit: int,
) -> EntityListResponse:
    del principal_id
    logger.debug("list_entities called", extra={"after_id": after_id, "limit": limit})
    filters: list[FilterReturn] = []
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        ENTITY_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal"]),
        after_id=after_id,
    )
    items = sorted(
        [
            entity_response(item.properties, item.references, item.uuid)
            for item in objects
        ],
        key=lambda item: item.entity_id,
    )

    return EntityListResponse(
        items=items,
        limit=limit,
        total_count=total_count,
        after_id=items[-1].entity_id if len(items) == limit and items else None,
    )


@trace()
async def get_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> EntityResponse | None:
    logger.debug("get_entity called", extra={"entity_id": entity_id})
    response = await client.collections.get(ENTITY_COLLECTION).query.fetch_object_by_id(
        entity_id,
        return_references=empty_reference_queries(["principal"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("entity not found", extra={"entity_id": entity_id})
        return None
    logger.debug("entity found", extra={"entity_id": entity_id})
    return entity_response(response.properties, response.references, response.uuid)


@trace()
async def create_entity(
    client: WeaviateAsyncClient,
    payload: EntityCreateRequest,
    principal_id: uuid.UUID,
) -> EntityResponse:
    logger.info(
        "create_entity called",
        extra={"principal_id": principal_id, "entity_type": payload.entity_type},
    )
    entity_id = new_uuid6()
    await upsert(
        client,
        ENTITY_COLLECTION,
        entity_id,
        properties={
            "entity_type": payload.entity_type,
            "name": payload.name,
            "description": payload.description,
            "short_description": payload.short_description,
            "aliases": payload.aliases or [],
            "wikidata_id": payload.wikidata_id,
            "nlcr_authority_id": payload.nlcr_authority_id,
        },
        references={"principal": principal_id},
        vector={
            vector_name: embedding
            for vector_name, embedding in {
                DEFAULT_NAME_VECTOR: payload.name_embedding,
                DEFAULT_FULLTEXT_VECTOR: payload.fulltext_embedding,
            }.items()
            if embedding is not None
        }
        or None,
    )
    return EntityResponse(
        entity_id=entity_id,
        principal_id=principal_id,
        entity_type=payload.entity_type,
        name=payload.name,
        description=payload.description,
        short_description=payload.short_description,
        aliases=payload.aliases,
        wikidata_id=payload.wikidata_id,
        nlcr_authority_id=payload.nlcr_authority_id,
    )


@trace()
async def patch_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
    payload: EntityPatchRequest,
) -> EntityResponse | None:
    logger.info("patch_entity called", extra={"entity_id": entity_id})
    response = await client.collections.get(ENTITY_COLLECTION).query.fetch_object_by_id(
        entity_id,
        include_vector=True,
        return_references=empty_reference_queries(["principal"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("patch_entity skipped missing entity", extra={"entity_id": entity_id})
        return None

    properties = dict(response.properties)
    for key, value in payload.model_dump(exclude_unset=True).items():
        # Entities are stored with text-array aliases; normalize null to empty list.
        if key == "aliases" and value is None:
            properties[key] = []
            continue
        properties[key] = value

    vector_payload: dict[str, list[float]] | None = None
    named_vectors: dict[str, list[float]] = {}
    for vector_name, vector_value in response.vector.items():
        if _is_flat_float_vector(vector_value):
            named_vectors[vector_name] = [float(item) for item in vector_value]
    if named_vectors:
        vector_payload = named_vectors

    await upsert(
        client,
        ENTITY_COLLECTION,
        entity_id,
        properties=properties,
        references={
            "principal": require_reference_uuid(response.references, "principal"),
        },
        vector=vector_payload,
    )

    updated = await client.collections.get(ENTITY_COLLECTION).query.fetch_object_by_id(
        entity_id,
        return_references=empty_reference_queries(["principal"]),
    )
    if updated is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.warning(
            "patch_entity could not read updated entity", extra={"entity_id": entity_id}
        )
        return None

    logger.info("patch_entity completed", extra={"entity_id": entity_id})
    return entity_response(updated.properties, updated.references, updated.uuid)


@trace()
async def delete_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> bool:
    logger.info("delete_entity called", extra={"entity_id": entity_id})
    entity = await get_entity(client, entity_id)
    if entity is None:
        logger.info(
            "delete_entity skipped missing entity", extra={"entity_id": entity_id}
        )
        return False
    entities = client.collections.get(ENTITY_COLLECTION)
    result = await entities.data.delete_by_id(entity_id)
    logger.info(
        "delete_entity completed", extra={"entity_id": entity_id, "deleted": result}
    )
    return result


@trace()
async def delete_entities(
    client: WeaviateAsyncClient,
    payload: EntityDeleteManyRequest,
) -> EntityDeleteManyResponse:
    logger.info(
        "delete_entities called",
        extra={
            "delete_all": payload.delete_all,
            "entity_type": payload.entity_type,
            "entity_ids_count": len(payload.entity_ids or []),
        },
    )

    if payload.delete_all:
        deleted_count = await _delete_entities_by_filters(client, [])
        return EntityDeleteManyResponse(mode="all", deleted_count=deleted_count)

    if payload.entity_ids:
        unique_ids = sorted(set(payload.entity_ids))
        deleted_count = 0
        for entity_id in unique_ids:
            deleted = await delete_entity(client, entity_id)
            deleted_count += int(deleted)
        return EntityDeleteManyResponse(mode="entity_ids", deleted_count=deleted_count)

    # Schema validation ensures entity_type is present when not delete_all/entity_ids.
    filters: list[FilterReturn] = [
        Filter.by_property("entity_type").equal(payload.entity_type)
    ]
    deleted_count = await _delete_entities_by_filters(client, filters)
    return EntityDeleteManyResponse(mode="entity_type", deleted_count=deleted_count)


async def _delete_entities_by_filters(
    client: WeaviateAsyncClient,
    filters: list[FilterReturn],
    batch_limit: int = 200,
) -> int:
    entities = client.collections.get(ENTITY_COLLECTION)
    deleted_count = 0

    while True:
        response = await entities.query.fetch_objects(
            filters=combine_filters(filters),
            limit=batch_limit,
            return_references=empty_reference_queries([]),
        )
        if not response.objects:
            break

        for item in response.objects:
            deleted = await entities.data.delete_by_id(item.uuid)
            deleted_count += int(deleted)

    logger.info("delete_entities completed", extra={"deleted_count": deleted_count})
    return deleted_count


# ---------------------------------------------------------------------------
# Backward-Compatible Aliases
# ---------------------------------------------------------------------------
