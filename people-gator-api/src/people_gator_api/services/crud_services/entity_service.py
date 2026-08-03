"""Service for entity endpoints."""

import uuid

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.entities import EntityListResponse
from people_gator_api.schemas.entities import EntityResponse
from people_gator_api.services.crud_services.annotation_service import list_descriptions
from people_gator_api.services.crud_services.annotation_service import list_document_mentions
from people_gator_api.services.crud_services.annotation_service import list_entity_names
from people_gator_api.services.crud_services.annotation_service import list_faces
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import DEFAULT_FULLTEXT_VECTOR
from people_gator_api.services.vector_service.schema import DEFAULT_NAME_VECTOR
from people_gator_api.services.vector_service.schema import ENTITY_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_NAME_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.weaviate_utils import combine_filters
from people_gator_api.services.weaviate_utils import delete_document_mention_tree
from people_gator_api.services.weaviate_utils import dual_named_vector_payload
from people_gator_api.services.weaviate_utils import entity_response
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import query_objects
from people_gator_api.services.weaviate_utils import refresh_entity_aggregates
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------


async def list_entities(
    client: WeaviateAsyncClient,
    after_id: uuid.UUID | None,
    limit: int,
) -> EntityListResponse:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    response = await client.collections.get(ENTITY_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [entity_response(item.properties) for item in objects],
        key=lambda item: item.entity_id,
    )
    if after_id is not None:
        items = [item for item in items if item.entity_id > after_id]
    page_items = items[:limit]
    return EntityListResponse(
        items=page_items,
        total=len(page_items),
        next_after_id=page_items[-1].entity_id if len(page_items) == limit and page_items else None,
    )


async def get_entity(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> EntityResponse | None:
    obj = await fetch_by_id(client, ENTITY_COLLECTION, "entity_id", entity_id)
    if obj is None:
        return None
    return entity_response(obj.properties)


async def create_entity(
    client: WeaviateAsyncClient,
    payload: EntityCreateRequest,
    principal_id: uuid.UUID,
) -> EntityResponse:
    entity_id = new_uuid6()
    await upsert(
        client,
        ENTITY_COLLECTION,
        entity_id,
        properties={
            "entity_id": entity_id,
            "principal_id": principal_id,
            "entity_type": payload.entity_type,
            "name": payload.name,
            "description": payload.description,
            "wikidata_id": None,
            "nlcr_authority_id": None,
        },
        references={"principal": principal_id},
        vector=dual_named_vector_payload(
            name_embedding=payload.name_embedding,
            fulltext_embedding=payload.fulltext_embedding,
            name_vector_name=DEFAULT_NAME_VECTOR,
            fulltext_vector_name=DEFAULT_FULLTEXT_VECTOR,
        ),
    )
    await refresh_entity_aggregates(client, entity_id)
    return EntityResponse(
        entity_id=entity_id,
        principal_id=principal_id,
        entity_type=payload.entity_type,
        name=payload.name,
        description=payload.description,
        wikidata_id=None,
        nlcr_authority_id=None,
    )


async def delete_entity(client: WeaviateAsyncClient, entity_id: uuid.UUID) -> bool:
    entity = await get_entity(client, entity_id)
    if entity is None:
        return False

    document_mentions = await list_document_mentions(client, entity_id, None, None, 1000)
    for document_mention in document_mentions:
        await delete_document_mention_tree(client, document_mention.document_mention_id)

    faces = await list_faces(client, None, entity_id, None, 1000)
    for face in faces:
        await client.collections.get(FACE_COLLECTION).data.delete_by_id(face.detection_id)

    descriptions = await list_descriptions(client, entity_id, None, 1000)
    for description in descriptions:
        await client.collections.get(DESCRIPTION_COLLECTION).data.delete_by_id(
            description.description_id
        )

    entity_names = await list_entity_names(client, entity_id, None, 1000)
    for entity_name in entity_names:
        await client.collections.get(ENTITY_NAME_COLLECTION).data.delete_by_id(
            entity_name.entity_name_id
        )

    await client.collections.get(ENTITY_COLLECTION).data.delete_by_id(entity_id)
    return True


# ---------------------------------------------------------------------------
# Backward-Compatible Aliases
# ---------------------------------------------------------------------------


list_identities = list_entities
get_identity = get_entity
create_identity = create_entity
delete_identity = delete_entity
