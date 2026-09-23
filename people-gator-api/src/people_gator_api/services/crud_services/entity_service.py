"""Service for entity endpoints."""

import logging
import uuid
from collections.abc import AsyncGenerator

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityEmbeddingInput,
    EntityEmbeddingUpdateRequest,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import AssignmentType, EntityType
from people_gator_api.services.crud_services.media_service import (
    entity_ids_for_source,
)
from people_gator_api.services.weaviate_service.assignments import (
    assigned_reference_ids,
)
from people_gator_api.weaviate_schema import (
    ENTITY_COLLECTION,
    model_vector_name,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_entity,
    reference_id_filter,
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


def _entity_vectors(
    embeddings: list[EntityEmbeddingInput],
) -> dict[str, list[float]] | None:
    vectors: dict[str, list[float]] = {}
    for embedding in embeddings:
        vector_name = model_vector_name(embedding.field, embedding.model_identifier)
        if vector_name in vectors:
            raise ValueError(
                f"duplicate entity embedding field/model pair: {embedding.field}/{embedding.model_identifier}"
            )
        vectors[vector_name] = embedding.vector
    return vectors or None


def _build_entity_filters(
    entity_type: EntityType | None,
    wikidata_id: str | None,
    nlcr_authority_id: str | None,
    user_id: uuid.UUID | None,
) -> list[FilterReturn]:
    filters: list[FilterReturn] = []

    if entity_type is not None:
        filters.append(Filter.by_property("entity_type").equal(entity_type.value))
    if wikidata_id is not None:
        filters.append(Filter.by_property("wikidata_id").equal(wikidata_id))
    if nlcr_authority_id is not None:
        filters.append(Filter.by_property("nlcr_authority_id").equal(nlcr_authority_id))
    if user_id is not None:
        filters.append(reference_id_filter(link_on="user", reference_id=user_id))
    return filters


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


@trace()
async def list_entities(
    client: WeaviateAsyncClient,
    user_id: uuid.UUID,
    after_id: uuid.UUID | None,
    limit: int,
    entity_type: EntityType | None = None,
    wikidata_id: str | None = None,
    nlcr_authority_id: str | None = None,
    owner_user_id: uuid.UUID | None = None,
    source_id: uuid.UUID | None = None,
    assignment: AssignmentType | None = None,
) -> EntityListResponse:
    del user_id
    filters = _build_entity_filters(
        entity_type=entity_type,
        wikidata_id=wikidata_id,
        nlcr_authority_id=nlcr_authority_id,
        user_id=owner_user_id,
    )
    if source_id is not None:
        entity_ids = await entity_ids_for_source(client, source_id)
        if not entity_ids:
            return EntityListResponse(
                items=[],
                limit=limit,
                total_count=0,
                cursor=None,
            )
        filters.append(Filter.by_id().contains_any(sorted(entity_ids)))
    if assignment is not None:
        assigned_entity_ids = await assigned_reference_ids(client, assignment, "entity")
        if not assigned_entity_ids:
            return EntityListResponse(
                items=[], limit=limit, total_count=0, cursor=None
            )
        filters.append(Filter.by_id().contains_any(sorted(assigned_entity_ids)))
    logger.debug(
        "list_entities called",
        extra={
            "after_id": after_id,
            "limit": limit,
            "entity_type": entity_type.value if entity_type is not None else None,
            "wikidata_id": wikidata_id,
            "nlcr_authority_id": nlcr_authority_id,
            "owner_user_id": owner_user_id,
            "source_id": source_id,
            "assignment": assignment.value if assignment is not None else None,
        },
    )
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        ENTITY_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["user"]),
        after_id=after_id,
    )
    items = sorted(
        [parse_entity(item.properties, item.references, item.uuid) for item in objects],
        key=lambda item: item.entity_id,
    )

    return EntityListResponse(
        items=items,
        limit=limit,
        total_count=total_count,
        cursor=items[-1].entity_id if len(items) == limit and items else None,
    )


@trace()
async def get_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> EntityResponse | None:
    logger.debug("get_entity called", extra={"entity_id": entity_id})
    response = await fetch_collection_object(
        client,
        ENTITY_COLLECTION,
        entity_id,
        reference_names=["user"],
    )
    if response is None:
        logger.info("entity not found", extra={"entity_id": entity_id})
        return None
    logger.debug("entity found", extra={"entity_id": entity_id})
    return parse_entity(response.properties, response.references, response.uuid)


@trace()
async def create_entity(
    client: WeaviateAsyncClient,
    payload: EntityCreateRequest,
    user_id: uuid.UUID,
) -> EntityResponse:
    logger.info(
        "create_entity called",
        extra={"user_id": user_id, "entity_type": payload.entity_type},
    )
    entity_id = new_uuid6()
    await client.collections.get(ENTITY_COLLECTION).data.insert(
        uuid=entity_id,
        properties={
            "entity_type": payload.entity_type,
            "name": payload.name,
            "description": payload.description,
            "short_description": payload.short_description,
            "aliases": payload.aliases or [],
            "wikidata_id": payload.wikidata_id,
            "nlcr_authority_id": payload.nlcr_authority_id,
        },
        references={"user": user_id},
        vector=_entity_vectors(payload.embeddings),
    )
    return EntityResponse(
        entity_id=entity_id,
        user_id=user_id,
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
    payload: AsyncGenerator[EntityCreateRequest],
    user_id: uuid.UUID,
) -> list[EntityResponse]:
    logger.info(
        "create_entity_batch called",
        extra={"user_id": user_id},
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
                references={"user": user_id},
                vector=_entity_vectors(entity_payload.embeddings),
            )
            ids.append(uuid.UUID(str(added_id)))
    # After batch is complete, fetch the created entities to return their details
    created_entities = await entity_collection.query.fetch_objects_by_ids(
        ids,
        return_references=empty_reference_queries(["user"]),
    )
    return [
        parse_entity(item.properties, item.references, item.uuid)
        for item in created_entities.objects
    ]


@trace()
async def update_entity_embeddings_batch(
    client: WeaviateAsyncClient,
    payloads: list[EntityEmbeddingUpdateRequest],
) -> int:
    """Upsert several named vectors per entity through one Weaviate batch."""
    collection = client.collections.use(ENTITY_COLLECTION)
    async with collection.batch.stream() as batch:
        for payload in payloads:
            await batch.add_object(
                uuid=payload.entity_id,
                vector=_entity_vectors(payload.embeddings),
            )
    return sum(len(payload.embeddings) for payload in payloads)


@trace()
async def patch_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
    payload: EntityPatchRequest,
) -> EntityResponse | None:
    logger.info("patch_entity called", extra={"entity_id": entity_id})
    response = await fetch_collection_object(
        client,
        ENTITY_COLLECTION,
        entity_id,
        reference_names=["user"],
    )
    if response is None:
        logger.info(
            "patch_entity skipped missing entity", extra={"entity_id": entity_id}
        )
        return None

    updates = payload.model_dump(exclude_unset=True)
    # Entities are stored with text-array aliases; normalize null to an empty list.
    if updates.get("aliases") is None and "aliases" in updates:
        updates["aliases"] = []

    await client.collections.get(ENTITY_COLLECTION).data.update(
        uuid=entity_id,
        properties=updates,
    )

    properties = dict(response.properties)
    properties.update(updates)

    logger.info("patch_entity completed", extra={"entity_id": entity_id})
    return parse_entity(properties, response.references, response.uuid)


@trace()
async def delete_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> bool:
    logger.info("delete_entity called", extra={"entity_id": entity_id})
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
        while True:
            deleted = await entities.data.delete_many(
                Filter.not_(Filter.by_property("entity_type").equal("unicorn"))
            )
            if deleted.matches == 0:
                break
            failed += deleted.failed
            matches += deleted.matches
            successful += deleted.successful

    logger.info(
        "delete_entities completed",
        extra={
            "deleted_count": successful,
            "failed_count": failed,
            "matches_count": matches,
        },
    )
    return successful


# ---------------------------------------------------------------------------
# Backward-Compatible Aliases
# ---------------------------------------------------------------------------
