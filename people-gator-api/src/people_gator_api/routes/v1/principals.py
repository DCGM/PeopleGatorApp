import uuid

from fastapi import (
    APIRouter,
    Depends,
)
from weaviate import (
    WeaviateAsyncClient,
)

from people_gator_api.services.database_service import (
    WeaviateSessionDependency,
)
from people_gator_api.schemas.enums import (
    PrincipalType,
)
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    ModelAgentPatchRequest,
    PrincipalResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    AnnotatorUserDependency,
)
from people_gator_api.services.http_errors import (
    raise_api_error,
)
from people_gator_api.services.crud_services.principal_service import (
    create_model_agent,
    get_principal,
    list_principals,
    update_principal,
)

router = APIRouter(tags=["principals"])


@router.get("/principals", response_model=list[PrincipalResponse])
async def list_principals_route(
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    principal_type: PrincipalType | None = None,
    is_active: bool | None = True,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
) -> list[PrincipalResponse]:
    return await list_principals(session, principal_type, is_active, after_id, limit)


@router.get("/principals/{principal_id}", response_model=PrincipalResponse)
async def get_principal_route(
    principal_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AnnotatorUserDependency,
) -> PrincipalResponse:
    found_principal = await get_principal(session, principal_id)
    if found_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return found_principal


@router.get("/principals/me", response_model=PrincipalResponse)
async def get_me_route(
    principal: AnnotatorUserDependency,
) -> PrincipalResponse:
    return PrincipalResponse(
        principal_id=principal.principal_id,
        principal_type=PrincipalType.user,
        display_name=principal.username,
        is_active=True,
    )


@router.post("/principals/model-agents", response_model=PrincipalResponse)
async def create_model_agent_route(
    payload: ModelAgentCreateRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> PrincipalResponse:
    return await create_model_agent(session, payload)


@router.patch("/principals/model-agents/{principal_id}", response_model=PrincipalResponse)
async def patch_model_agent_route(
    principal_id: uuid.UUID,
    payload: ModelAgentPatchRequest,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> PrincipalResponse:
    updated_principal = await update_principal(
        session,
        principal_id,
        payload.display_name,
        payload.is_active,
    )
    if updated_principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return updated_principal
