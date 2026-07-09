"""Service for consensus endpoints (spec §2.6).

Annotators create immutable LINK_DECISION records.  A separate explicit
LINK_CONSENSUS snapshot is then created from these decisions and attached
to the identity as its current state.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.models.link import LinkConsensus, LinkDecision
from people_gator_api.schemas.identities import (
    BulkLinkDecisionRequest,
    BulkLinkDecisionResponse,
    LinkConsensusCreateRequest,
    LinkConsensusResponse,
    LinkDecisionCreateRequest,
    LinkDecisionResponse,
)


def _decision_out(item: LinkDecision) -> LinkDecisionResponse:
    return LinkDecisionResponse(
        identity_id=item.identity_id,
        annotation_id=item.annotation_id,
        principal_id=item.principal_id,
        confidence=item.confidence,
        created_at=item.created_at,
    )


def _consensus_out(item: LinkConsensus) -> LinkConsensusResponse:
    return LinkConsensusResponse(
        identity_id=item.identity_id,
        annotation_id=item.annotation_id,
        principal_id=item.principal_id,
        method=item.method,
        created_at=item.created_at,
    )


async def create_decision(
    session: AsyncSession,
    payload: LinkDecisionCreateRequest,
    principal_id: uuid.UUID,
) -> LinkDecisionResponse:
    decision = await LinkDecision.create(
        session=session,
        identity_id=payload.identity_id,
        annotation_id=payload.annotation_id,
        principal_id=principal_id,
        confidence=payload.confidence,
    )
    return _decision_out(decision)

async def bulk_create_decisions(
    session: AsyncSession,
    payload: BulkLinkDecisionRequest,
    principal_id: uuid.UUID,
) -> BulkLinkDecisionResponse:
    created: list[LinkDecisionResponse] = []
    for item in payload.decisions:
        decision = await LinkDecision.create(
            session=session,
            identity_id=item.identity_id,
            annotation_id=item.annotation_id,
            principal_id=principal_id,
            confidence=item.confidence,
        )
        created.append(_decision_out(decision))
    return BulkLinkDecisionResponse(created=created)


async def list_decisions_for_identity(
    session: AsyncSession,
    identity_id: uuid.UUID,
) -> list[LinkDecisionResponse]:
    rows = await LinkDecision.list_for_identity(session, identity_id)
    return [_decision_out(row) for row in rows]


async def create_consensus(
    session: AsyncSession,
    payload: LinkConsensusCreateRequest,
    created_by: uuid.UUID,
) -> LinkConsensusResponse:
    consensus = await LinkConsensus.create(
        session=session,
        identity_id=payload.identity_id,
        annotation_id=payload.annotation_id,
        method=payload.method,
        created_by=created_by,
    )
    return _consensus_out(consensus)


async def list_consensus_for_identity(
    session: AsyncSession,
    identity_id: uuid.UUID,
) -> list[LinkConsensusResponse]:
    rows = await LinkConsensus.list_for_identity(session, identity_id)
    return [_consensus_out(row) for row in rows]
