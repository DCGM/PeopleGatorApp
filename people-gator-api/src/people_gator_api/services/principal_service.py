import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import PrincipalType
from people_gator_api.db.models.principal import ModelAgent, Principal, ServiceAgent
from people_gator_api.schemas.principals import ModelAgentCreateRequest, PrincipalResponse, ServiceAgentCreateRequest


async def list_principals(
    session: AsyncSession,
    principal_type: PrincipalType | None,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[PrincipalResponse]:
    stmt = sa.select(Principal).order_by(Principal.principal_id.asc()).limit(limit)
    if principal_type is not None:
        stmt = stmt.where(Principal.principal_type == principal_type)
    if is_active is not None:
        stmt = stmt.where(Principal.is_active == is_active)
    if after_id is not None:
        stmt = stmt.where(Principal.principal_id > after_id)

    result = await session.execute(stmt)
    return [
        PrincipalResponse(
            principal_id=item.principal_id,
            principal_type=item.principal_type,
            display_name=item.display_name,
            is_active=item.is_active,
        )
        for item in result.scalars().all()
    ]


async def get_principal(session: AsyncSession, principal_id: uuid.UUID) -> PrincipalResponse | None:
    principal = await Principal.get(session, principal_id)
    if principal is None:
        return None
    return PrincipalResponse(
        principal_id=principal.principal_id,
        principal_type=principal.principal_type,
        display_name=principal.display_name,
        is_active=principal.is_active,
    )


async def create_service_agent(session: AsyncSession, payload: ServiceAgentCreateRequest) -> PrincipalResponse:
    agent, _ = await ServiceAgent.get_or_create(
        session=session,
        agent_slug=payload.agent_slug,
        display_name=payload.display_name,
        description=payload.description,
    )
    return PrincipalResponse(
        principal_id=agent.principal_id,
        principal_type=agent.principal_type,
        display_name=agent.display_name,
        is_active=agent.is_active,
    )


async def create_model_agent(session: AsyncSession, payload: ModelAgentCreateRequest) -> PrincipalResponse:
    agent = await ModelAgent.get_by_slot(
        session=session,
        evidence_type=payload.evidence_type,
        role=payload.role,
        model_slug=payload.model_slug,
    )
    if agent is None:
        agent = ModelAgent(
            principal_id=uuid.uuid4(),
            principal_type=PrincipalType.model_agent,
            display_name=payload.display_name,
            is_active=payload.is_active,
            evidence_type=payload.evidence_type,
            role=payload.role,
            model_slug=payload.model_slug,
            model_version=payload.model_version,
            registry_source=payload.registry_source,
            registry_uri=payload.registry_uri,
        )
        session.add(agent)
    agent.is_active = payload.is_active
    session.add(agent)
    return PrincipalResponse(
        principal_id=agent.principal_id,
        principal_type=agent.principal_type,
        display_name=agent.display_name,
        is_active=agent.is_active,
    )
