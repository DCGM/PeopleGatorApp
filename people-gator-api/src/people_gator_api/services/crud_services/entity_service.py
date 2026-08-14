"""Service for entity endpoints."""

from datetime import datetime
import logging
import uuid
from typing import TypeGuard
from collections.abc import AsyncGenerator

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.enums import EntityType
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
    reference_id_filter,
    upsert,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)

NON_FILTERABLE_ENTITY_PROPERTIES: frozenset[str] = frozenset(
    {"name", "aliases", "description", "short_description"}
)
FILTERABLE_ENTITY_PROPERTIES: frozenset[str] = frozenset(
    {"entity_type", "wikidata_id", "nlcr_authority_id"}
)


def _is_flat_float_vector(
    value: list[float] | list[list[float]],
) -> TypeGuard[list[float]]:
    return all(isinstance(item, (int, float)) for item in value)


def _build_entity_filters(
    entity_type: EntityType | None,
    wikidata_id: str | None,
    nlcr_authority_id: str | None,
    principal_id: uuid.UUID | None,
) -> list[FilterReturn]:
    filters: list[FilterReturn] = []

    if entity_type is not None:
        filters.append(Filter.by_property("entity_type").equal(entity_type.value))
    if wikidata_id is not None:
        filters.append(Filter.by_property("wikidata_id").equal(wikidata_id))
    if nlcr_authority_id is not None:
        filters.append(Filter.by_property("nlcr_authority_id").equal(nlcr_authority_id))
    if principal_id is not None:
        filters.append(reference_id_filter(link_on="principal", reference_id=principal_id))
    return filters


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@trace()
async def list_entities(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    after_id: uuid.UUID | None,
    limit: int,
    entity_type: EntityType | None = None,
    wikidata_id: str | None = None,
    nlcr_authority_id: str | None = None,
    owner_principal_id: uuid.UUID | None = None,
) -> EntityListResponse:
    del principal_id
    filters = _build_entity_filters(
        entity_type=entity_type,
        wikidata_id=wikidata_id,
        nlcr_authority_id=nlcr_authority_id,
        principal_id=owner_principal_id,
    )
    logger.debug(
        "list_entities called",
        extra={
            "after_id": after_id,
            "limit": limit,
            "entity_type": entity_type.value if entity_type is not None else None,
            "wikidata_id": wikidata_id,
            "nlcr_authority_id": nlcr_authority_id,
            "owner_principal_id": owner_principal_id,
        },
    )
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
async def create_entity_batch(
    client: WeaviateAsyncClient,
    payload: AsyncGenerator[EntityCreateRequest, None],
    principal_id: uuid.UUID,
) -> list[EntityResponse]:
    logger.info(
        "create_entity_batch called",
        extra={"principal_id": principal_id},
    )
    entity_collection = client.collections.use(ENTITY_COLLECTION)
    ids: list[uuid.UUID] = []
    async with entity_collection.batch.stream() as batch:
        async for entity_payload in payload:
            entity_id = new_uuid6()
            added_id = await batch.add_object(
                uuid=entity_id,
                properties={
                    "entity_type": entity_payload.entity_type,
                    "name": entity_payload.name,
                    "description": entity_payload.description,
                    "short_description": entity_payload.short_description,
                    "aliases": entity_payload.aliases or [],
                    "wikidata_id": entity_payload.wikidata_id,
                    "nlcr_authority_id": entity_payload.nlcr_authority_id,
                },
                references={"principal": principal_id},
                vector={
                    vector_name: embedding
                    for vector_name, embedding in {
                        DEFAULT_NAME_VECTOR: entity_payload.name_embedding,
                        DEFAULT_FULLTEXT_VECTOR: entity_payload.fulltext_embedding,
                    }.items()
                    if embedding is not None
                }
                or None,
            )
            ids.append(uuid.UUID(str(added_id)))
    # After batch is complete, fetch the created entities to return their details
    created_entities = await entity_collection.query.fetch_objects_by_ids(
        ids,
        return_references=empty_reference_queries(["principal"]),
    )
    return [
        entity_response(item.properties, item.references, item.uuid)
        for item in created_entities.objects
    ]


@trace()
async def patch_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
    principal_id: uuid.UUID,
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
            "principal": principal_id,
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
) -> int:
    entities = client.collections.get(ENTITY_COLLECTION)
    failed: int = 0
    matches: int = 0
    successful: int = 0
    filters_combined = combine_filters(filters)
    
    if filters_combined is not None:
        deleted = await entities.data.delete_many(where=filters_combined)
        failed = deleted.failed
        matches = deleted.matches
        successful = deleted.successful
    else:
        # If no filters are provided, delete all entities in the collection.
        deleted = await entities.data.delete_many(
            Filter.by_creation_time().greater_than(datetime.fromtimestamp(0))
        )
        failed = deleted.failed
        matches = deleted.matches
        successful = deleted.successful

    logger.info("delete_entities completed", extra={
        "deleted_count": successful,
        "failed_count": failed,
        "matches_count": matches,
    })
    return successful


# ---------------------------------------------------------------------------
# Backward-Compatible Aliases
# ---------------------------------------------------------------------------
