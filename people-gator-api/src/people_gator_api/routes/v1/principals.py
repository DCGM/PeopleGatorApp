import asyncio
import uuid

from fastapi import APIRouter, Query
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    ModelAgentListResponse,
    ModelAgentPatchRequest,
    ModelAgentResponse,
    PrincipalListResponse,
    PrincipalResponse,
    UserListResponse,
    UserResponse,
    UserPatchRequest,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
)
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.principal_service import (
    create_model_agent,
    delete_model_agent,
    get_model_agent,
    get_principal,
    get_user,
    list_model_agents,
    list_principals,
    list_users,
    update_model_agent,
    update_user,
)
from people_gator_api.services.sse import (
    BrokerDependency,
    DeletedResourceEvent,
    SseEventType,
)

router = APIRouter(tags=["principals"])


@router.get("/me", response_model=PrincipalResponse)
async def get_me_route(
    principal: AnnotatorUserDependency,
) -> PrincipalResponse:
    response = PrincipalResponse(
        principal_id=principal.principal_id,
        principal_type=PrincipalType.user,
        display_name=principal.display_name,
        is_active=True,
    )
    return response


@router.get("/principals", response_model=PrincipalListResponse)
async def list_principals_route(
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    principal_type: PrincipalType | None = None,
    is_active: bool | None = True,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> PrincipalListResponse:
    return await list_principals(
        session,
        principal.principal_id,
        principal_type,
        is_active,
        after_id,
        limit,
    )


@router.get("/principals/{principal_id}", response_model=PrincipalResponse)
async def get_principal_route(
    principal_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
) -> PrincipalResponse:
    found_principal = await get_principal(
        session,
        principal.principal_id,
        principal_id,
    )
    if found_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return found_principal


@router.get("/model-agents", response_model=ModelAgentListResponse)
async def list_model_agents_route(
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    is_active: bool | None = True,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> ModelAgentListResponse:
    return await list_model_agents(
        session,
        principal.principal_id,
        is_active,
        after_id,
        limit,
    )


@router.post("/model-agents", response_model=ModelAgentResponse)
async def create_model_agent_route(
    payload: ModelAgentCreateRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> ModelAgentResponse:
    model_agent = await create_model_agent(session, payload, principal.principal_id)
    asyncio.create_task(broker.publish(
        ("principals", model_agent.principal_id),
        ("model-agents", model_agent.principal_id),
        event=SseEventType.MODEL_AGENT_CREATED,
        data=model_agent,
    ))
    return model_agent


@router.get("/model-agents/{principal_id}", response_model=ModelAgentResponse)
async def get_model_agent_route(
    principal_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> ModelAgentResponse:
    found_principal = await get_model_agent(
        session,
        principal.principal_id,
        principal_id,
    )
    if found_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return found_principal


@router.patch("/model-agents/{principal_id}", response_model=ModelAgentResponse)
async def patch_model_agent_route(
    principal_id: uuid.UUID,
    payload: ModelAgentPatchRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> ModelAgentResponse:
    updated_principal = await update_model_agent(
        session,
        principal.principal_id,
        principal_id,
        payload,
    )
    if updated_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    asyncio.create_task(broker.publish(
        ("principals", updated_principal.principal_id),
        ("model-agents", updated_principal.principal_id),
        event=SseEventType.MODEL_AGENT_UPDATED,
        data=updated_principal,
    ))
    return updated_principal


@router.delete("/model-agents/{principal_id}", status_code=204)
async def delete_model_agent_route(
    principal_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> None:
    deleted = await delete_model_agent(session, principal.principal_id, principal_id)
    if not deleted:
        raise_api_error(404, "not_found", "Principal not found")
    asyncio.create_task(broker.publish(
        ("principals", principal_id),
        ("model-agents", principal_id),
        event=SseEventType.MODEL_AGENT_DELETED,
        data=DeletedResourceEvent(resource_id=principal_id),
    ))


@router.get("/users", response_model=UserListResponse)
async def list_users_route(
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    is_active: bool | None = True,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> UserListResponse:
    return await list_users(
        session,
        principal.principal_id,
        is_active,
        after_id,
        limit,
    )


@router.get("/users/{principal_id}", response_model=UserResponse)
async def get_user_route(
    principal_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> UserResponse:
    found_user = await get_user(
        session,
        principal.principal_id,
        principal_id,
    )
    if found_user is None:
        raise_api_error(404, "not_found", "User not found")
    return found_user


@router.patch("/users/{principal_id}", response_model=UserResponse)
async def patch_user_route(
    principal_id: uuid.UUID,
    payload: UserPatchRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> UserResponse:
    updated_principal = await update_user(
        session,
        principal.principal_id,
        principal_id,
        payload,
    )
    if updated_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    asyncio.create_task(broker.publish(
        ("principals", updated_principal.principal_id),
        ("users", updated_principal.principal_id),
        event=SseEventType.USER_UPDATED,
        data=updated_principal,
    ))
    return updated_principal
