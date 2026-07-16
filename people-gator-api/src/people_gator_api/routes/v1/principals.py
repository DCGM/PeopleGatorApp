import uuid

from fastapi import APIRouter, Depends
from weaviate import WeaviateAsyncClient

from people_gator_api.services.database_service import get_session
from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    ModelAgentPatchRequest,
    PrincipalResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.crud_services.principal_service import (
    create_model_agent,
    get_principal,
    list_principals,
    update_principal,
)

router = APIRouter(tags=["principals"])


@router.get("/principals", response_model=list[PrincipalResponse])
async def list_principals_route(
    principal_type: PrincipalType | None = None,
    is_active: bool | None = True,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> list[PrincipalResponse]:
    return await list_principals(session, principal_type, is_active, after_id, limit)


@router.get("/principals/{principal_id}", response_model=PrincipalResponse)
async def get_principal_route(
    principal_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> PrincipalResponse:
    principal = await get_principal(session, principal_id)
    if principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return principal


@router.get("/principals/me", response_model=PrincipalResponse)
async def get_me_route(
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
) -> PrincipalResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    assert auth.principal is not None
    return PrincipalResponse(
        principal_id=auth.principal.principal_id,
        principal_type=auth.principal.principal_type,
        display_name=auth.principal.display_name,
        is_active=auth.principal.is_active,
    )


@router.post("/principals/model-agents", response_model=PrincipalResponse)
async def create_model_agent_route(
    payload: ModelAgentCreateRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> PrincipalResponse:
    return await create_model_agent(session, payload)


@router.patch("/principals/model-agents/{principal_id}", response_model=PrincipalResponse)
async def patch_model_agent_route(
    principal_id: uuid.UUID,
    payload: ModelAgentPatchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:admin")),
    session: WeaviateAsyncClient = Depends(get_session),
) -> PrincipalResponse:
    principal = await update_principal(
        session,
        principal_id,
        payload.display_name,
        payload.is_active,
    )
    if principal is None:
        raise_api_error(404, "not_found", "Principal not found")
    return principal
