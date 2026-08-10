"""Service for entity endpoints."""

import logging
import uuid

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListResponse,
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
    upsert,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


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
    response = await client.collections.get(ENTITY_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal"]),
        after=after_id,
    )
    items = sorted(
        [
            entity_response(item.properties, item.references, item.uuid)
            for item in response.objects
        ],
        key=lambda item: item.entity_id,
    )
    return EntityListResponse(
        items=items,
        limit=limit,
        total_count=len(items),
        after_id=items[-1].entity_id if len(items) == limit and items else None,
    )


@trace()
async def get_entity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> EntityResponse | None:
    del principal_id
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
            "aliases": [{"alias": alias} for alias in (payload.aliases or [])],
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
async def delete_entity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> bool:
    logger.info("delete_entity called", extra={"entity_id": entity_id})
    entity = await get_entity(client, principal_id, entity_id)
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


# ---------------------------------------------------------------------------
# Backward-Compatible Aliases
# ---------------------------------------------------------------------------
