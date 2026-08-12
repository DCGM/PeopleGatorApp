"""Entity endpoints (spec §2.1)."""

import asyncio
from collections.abc import AsyncGenerator
import uuid

from fastapi import (
    APIRouter,
    status,
)

from people_gator_api.schemas.entities import (
    DocumentMentionListResponse,
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
    FaceListResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
    BrowseUserDependency,
)
from people_gator_api.services.crud_services.annotation_service import (
    list_document_mentions,
    list_faces,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.sse import (
    BrokerDependency,
    DeletedResourceEvent,
    SseEventType,
)
from people_gator_api.services.crud_services.entity_service import (
    create_entity,
    create_entity_batch,
    delete_entities,
    delete_entity,
    get_entity,
    list_entities,
    patch_entity,
)

router = APIRouter(tags=["entities"])


@router.get("/entities", response_model=EntityListResponse)
async def list_entities_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> EntityListResponse:
    return await list_entities(session, principal.principal_id, after_id, limit)


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> EntityResponse:
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    return entity


@router.get(
    "/entities/{entity_id}/document-mentions",
    response_model=DocumentMentionListResponse,
)
async def list_entity_document_mentions_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> DocumentMentionListResponse:
    return await list_document_mentions(
        session,
        principal.principal_id,
        entity_id,
        None,
        after_id,
        limit,
    )


@router.get("/entities/{entity_id}/faces", response_model=FaceListResponse)
async def list_entity_faces_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> FaceListResponse:
    return await list_faces(
        session,
        principal.principal_id,
        None,
        entity_id,
        after_id,
        limit,
    )


@router.post(
    "/entities", response_model=EntityResponse, status_code=status.HTTP_201_CREATED
)
async def create_entity_route(
    payload: EntityCreateRequest,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
    broker: BrokerDependency,
) -> EntityResponse:
    entity = await create_entity(session, payload, principal.principal_id)
    asyncio.create_task(broker.publish_to_topics(
        ("entities", entity.entity_id),
        ("principals", entity.principal_id, "entities", entity.entity_id),
        event=SseEventType.ENTITY_CREATED,
        data=entity,
    ))
    return entity


async def _publish_batch_of_entities(entities: list[EntityResponse], broker: BrokerDependency) -> None:
    await asyncio.gather(
        *(
            broker.publish_to_topics(
                ("entities", entity.entity_id),
                ("principals", entity.principal_id, "entities", entity.entity_id),
                event=SseEventType.ENTITY_CREATED,
                data=entity,
            )
            for entity in entities
        )
    )

@router.post(
    "/entities:batch", response_model=list[EntityResponse], status_code=status.HTTP_201_CREATED
)
async def create_entity_batch_route(
    payload: list[EntityCreateRequest],
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
    broker: BrokerDependency,
) -> list[EntityResponse]:
    async def async_list(iterable: list[EntityCreateRequest]) -> AsyncGenerator[EntityCreateRequest, None]:
        for item in iterable:
            yield item
    entities = await create_entity_batch(session, async_list(payload), principal.principal_id)
    asyncio.create_task(_publish_batch_of_entities(entities, broker))
    return entities


@router.patch("/entities/{entity_id}", response_model=EntityResponse)
async def patch_entity_route(
    entity_id: uuid.UUID,
    payload: EntityPatchRequest,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
    broker: BrokerDependency,
) -> EntityResponse:
    entity = await patch_entity(session, entity_id, principal.principal_id, payload)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    asyncio.create_task(broker.publish_to_topics(
        ("entities", entity.entity_id),
        ("principals", entity.principal_id, "entities", entity.entity_id),
        event=SseEventType.ENTITY_UPDATED,
        data=entity,
    ))
    return entity


@router.delete("/entities/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_entity_route(
    entity_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> None:
    del principal
    entity = await get_entity(session, entity_id)
    if entity is None:
        raise_api_error(404, "not_found", "Entity not found")
    deleted = await delete_entity(session, entity_id)
    if not deleted:
        raise_api_error(404, "not_found", "Entity not found")
    asyncio.create_task(broker.publish_to_topics(
        ("entities", entity_id),
        ("principals", entity.principal_id, "entities", entity_id),
        event=SseEventType.ENTITY_DELETED,
        data=DeletedResourceEvent(resource_id=entity_id),
    ))


@router.delete(
    "/entities",
    response_model=EntityDeleteManyResponse,
    status_code=status.HTTP_200_OK,
)
async def delete_entities_route(
    payload: EntityDeleteManyRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> EntityDeleteManyResponse:
    del principal
    response = await delete_entities(session, payload)
    asyncio.create_task(broker.publish_to_topics(
        ("entities",),
        event=SseEventType.ENTITY_DELETED,
        data=response,
    ))
    return response
