"""Service for entity endpoints."""

import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.classes.query import Sort

from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.entities import EntityListResponse
from people_gator_api.schemas.entities import EntityResponse
from people_gator_api.schemas.entities import EntityViewResponse
from people_gator_api.services.crud_services.annotation_service import list_descriptions
from people_gator_api.services.crud_services.annotation_service import list_document_mentions
from people_gator_api.services.crud_services.annotation_service import list_faces
from people_gator_api.services.crud_services.annotation_service import list_names
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.vector_service.schema import NAME_COLLECTION
from people_gator_api.services.weaviate_utils import combine_filters
from people_gator_api.services.weaviate_utils import delete_document_mention_tree
from people_gator_api.services.weaviate_utils import entity_response
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import refresh_entity_aggregates
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


async def list_entities(
    client: WeaviateAsyncClient,
    after_id: uuid.UUID | None,
    limit: int,
) -> EntityListResponse:
    filters = (
        [Filter.by_property("entity_id").greater_than(str(after_id))]
        if after_id is not None
        else []
    )
    response = await client.collections.get(ENTITY_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        sort=Sort.by_property("entity_id", ascending=True),
        limit=limit,
    )
    items = [entity_response(item.properties) for item in response.objects]
    return EntityListResponse(
        items=items,
        total=len(items),
        next_after_id=items[-1].entity_id if len(items) == limit and items else None,
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
            "name": payload.name,
            "description": payload.description,
            "face_count": 0,
            "mention_count": 0,
            "information_count": 0,
            "document_mention_count": 0,
            "name_count": 0,
            "description_count": 0,
        },
        references={"principal": principal_id},
        vector={},
    )
    await refresh_entity_aggregates(client, entity_id)
    return EntityResponse(
        entity_id=entity_id,
        principal_id=principal_id,
        name=payload.name,
        description=payload.description,
    )


async def get_entity_view(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID,
) -> EntityViewResponse | None:
    entity = await get_entity(client, entity_id)
    if entity is None:
        return None

    document_mentions = await list_document_mentions(client, entity_id, None, None, 500)
    faces = await list_faces(client, None, entity_id, None, 500)
    descriptions = await list_descriptions(client, entity_id, None, 500)
    names = await list_names(client, entity_id, None, 500)
    return EntityViewResponse(
        entity_id=entity_id,
        document_mention_ids=[item.document_mention_id for item in document_mentions],
        face_ids=[item.detection_id for item in faces],
        description_ids=[item.description_id for item in descriptions],
        name_ids=[item.name_id for item in names],
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

    names = await list_names(client, entity_id, None, 1000)
    for name in names:
        await client.collections.get(NAME_COLLECTION).data.delete_by_id(name.name_id)

    await client.collections.get(ENTITY_COLLECTION).data.delete_by_id(entity_id)
    return True


list_identities = list_entities
get_identity = get_entity
create_identity = create_entity
get_identity_view = get_entity_view
delete_identity = delete_entity
