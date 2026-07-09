"""Consensus endpoints (spec §2.6).

Annotators create immutable LINK_DECISION records.  A separate explicit
LINK_CONSENSUS snapshot is then created from these decisions.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.schemas.identities import (
    BulkLinkDecisionRequest,
    BulkLinkDecisionResponse,
    LinkConsensusCreateRequest,
    LinkConsensusResponse,
    LinkDecisionCreateRequest,
    LinkDecisionResponse,
)
from people_gator_api.services.auth_service import AuthContext, require_scopes
from people_gator_api.services.crud_services.consensus_service import (
    bulk_create_decisions,
    create_consensus,
    create_decision,
    list_consensus_for_identity,
    list_decisions_for_identity,
)
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["consensus"])


@router.post("/identities/{identity_id}/decisions", response_model=LinkDecisionResponse, status_code=status.HTTP_201_CREATED)
async def create_decision_route(
    identity_id: uuid.UUID,
    payload: LinkDecisionCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> LinkDecisionResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    if payload.identity_id != identity_id:
        raise_api_error(400, "mismatch", "identity_id in body does not match path")
    return await create_decision(session, payload, auth.principal.principal_id)


@router.post("/identities/{identity_id}/decisions/bulk", response_model=BulkLinkDecisionResponse, status_code=status.HTTP_201_CREATED)
async def bulk_create_decisions_route(
    identity_id: uuid.UUID,
    payload: BulkLinkDecisionRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> BulkLinkDecisionResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    for item in payload.decisions:
        if item.identity_id != identity_id:
            raise_api_error(400, "mismatch", "identity_id in body does not match path")
    return await bulk_create_decisions(session, payload, auth.principal.principal_id)


@router.get("/identities/{identity_id}/decisions", response_model=list[LinkDecisionResponse])
async def list_decisions_route(
    identity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:review")),
    session: AsyncSession = Depends(get_session),
) -> list[LinkDecisionResponse]:
    return await list_decisions_for_identity(session, identity_id)


@router.post("/identities/{identity_id}/consensus", response_model=LinkConsensusResponse, status_code=status.HTTP_201_CREATED)
async def create_consensus_route(
    identity_id: uuid.UUID,
    payload: LinkConsensusCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:verify")),
    session: AsyncSession = Depends(get_session),
) -> LinkConsensusResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    if payload.identity_id != identity_id:
        raise_api_error(400, "mismatch", "identity_id in body does not match path")
    return await create_consensus(session, payload, auth.principal.principal_id)


@router.get("/identities/{identity_id}/consensus", response_model=list[LinkConsensusResponse])
async def list_consensus_route(
    identity_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:review")),
    session: AsyncSession = Depends(get_session),
) -> list[LinkConsensusResponse]:
    return await list_consensus_for_identity(session, identity_id)
