import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.enums import ClusterRole, EvidenceType
from people_gator_api.db.models.search_profile import SearchProfile, SearchProfileModality
from people_gator_api.db.models.version import Version
from people_gator_api.schemas.search import (
    SearchFacetsResponse,
    SearchFilters,
    SearchProfileCloneRequest,
    SearchProfileCreateRequest,
    SearchProfileModalityOut,
    SearchProfileResponse,
    SearchProfileUpdateRequest,
    SearchQuery,
    SearchRequest,
    SearchResponse,
)


def _profile_to_response(profile: SearchProfile) -> SearchProfileResponse:
    modalities = [
        SearchProfileModalityOut(
            evidence_type=row.evidence_type,
            weight=row.weight,
            model_id=row.model_id,
            enabled=row.enabled,
            min_confidence=row.min_confidence,
        )
        for row in profile.modalities
    ]
    return SearchProfileResponse(
        profile_id=profile.profile_id,
        profile_name=profile.profile_name,
        description=profile.description,
        owner_id=profile.owner_id,
        is_public=profile.is_public,
        is_system=profile.is_system,
        modalities=modalities,
    )


async def list_profiles(session: AsyncSession, principal_id: uuid.UUID | None, include_system: bool, include_public: bool) -> list[SearchProfileResponse]:
    stmt = select(SearchProfile).order_by(SearchProfile.profile_name.asc())
    rows = list((await session.execute(stmt)).scalars().all())
    filtered: list[SearchProfileResponse] = []
    for row in rows:
        if row.owner_id == principal_id:
            filtered.append(_profile_to_response(row))
            continue
        if include_system and row.is_system:
            filtered.append(_profile_to_response(row))
            continue
        if include_public and row.is_public:
            filtered.append(_profile_to_response(row))
    return filtered


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> SearchProfileResponse | None:
    profile = await session.scalar(select(SearchProfile).where(SearchProfile.profile_id == profile_id))
    if profile is None:
        return None
    return _profile_to_response(profile)


async def create_profile(session: AsyncSession, owner_id: uuid.UUID, request: SearchProfileCreateRequest) -> SearchProfileResponse:
    profile = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name=request.profile_name,
        description=request.description,
        owner_id=owner_id,
        is_public=request.is_public,
        is_system=False,
    )
    session.add(profile)
    for modality in request.modalities:
        session.add(
            SearchProfileModality(
                profile_id=profile.profile_id,
                evidence_type=modality.evidence_type,
                weight=modality.weight,
                model_id=modality.model_id,
                enabled=modality.enabled,
                min_confidence=modality.min_confidence,
            )
        )
    await session.flush()
    await session.refresh(profile)
    return _profile_to_response(profile)


async def update_profile(session: AsyncSession, profile_id: uuid.UUID, request: SearchProfileUpdateRequest) -> SearchProfileResponse | None:
    profile = await session.scalar(select(SearchProfile).where(SearchProfile.profile_id == profile_id))
    if profile is None:
        return None
    if request.profile_name is not None:
        profile.profile_name = request.profile_name
    if request.description is not None:
        profile.description = request.description
    if request.is_public is not None:
        profile.is_public = request.is_public
    if request.modalities is not None:
        await session.execute(delete(SearchProfileModality).where(SearchProfileModality.profile_id == profile_id))
        for modality in request.modalities:
            session.add(
                SearchProfileModality(
                    profile_id=profile.profile_id,
                    evidence_type=modality.evidence_type,
                    weight=modality.weight,
                    model_id=modality.model_id,
                    enabled=modality.enabled,
                    min_confidence=modality.min_confidence,
                )
            )
    await session.flush()
    await session.refresh(profile)
    return _profile_to_response(profile)


async def delete_profile(session: AsyncSession, profile_id: uuid.UUID) -> bool:
    profile = await session.scalar(select(SearchProfile).where(SearchProfile.profile_id == profile_id))
    if profile is None:
        return False
    await session.delete(profile)
    return True


async def clone_profile(session: AsyncSession, profile_id: uuid.UUID, owner_id: uuid.UUID, request: SearchProfileCloneRequest) -> SearchProfileResponse | None:
    source = await session.scalar(select(SearchProfile).where(SearchProfile.profile_id == profile_id))
    if source is None:
        return None
    cloned = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name=request.profile_name or f"{source.profile_name}-clone",
        description=source.description,
        owner_id=owner_id,
        is_public=False,
        is_system=False,
    )
    session.add(cloned)
    for modality in source.modalities:
        session.add(
            SearchProfileModality(
                profile_id=cloned.profile_id,
                evidence_type=modality.evidence_type,
                weight=modality.weight,
                model_id=modality.model_id,
                enabled=modality.enabled,
                min_confidence=modality.min_confidence,
            )
        )
    await session.flush()
    await session.refresh(cloned)
    return _profile_to_response(cloned)


async def search(session: AsyncSession, request: SearchRequest) -> SearchResponse:
    search_cluster_id: uuid.UUID | None = None
    if request.save:
        cluster = await Cluster.create(session)
        version = await Version.create(
            session,
            cluster_id=cluster.cluster_id,
            cluster_role=ClusterRole.saved_search,
            actor_id=uuid.uuid4(),
            search_profile_id=request.profile_id,
        )
        cluster.head_version_id = version.version_id
        search_cluster_id = cluster.cluster_id

    facets = SearchFacetsResponse(
        cluster_roles={role.value: 0 for role in ClusterRole},
        provider={},
        result_types={value: 0 for value in request.result_types},
        evidence_types={evidence_type.value: 0 for evidence_type in EvidenceType},
        has_face={"true": 0, "false": 0},
        has_authority_link={"true": 0, "false": 0},
    )

    return SearchResponse(
        total=0,
        limit=request.limit,
        next_after_id=None,
        results=[],
        facets=facets.model_dump(),
        query=request.query,
        filters=request.filters,
        profile_id=request.profile_id,
        search_cluster_id=search_cluster_id,
    )


async def search_facets(_session: AsyncSession, _query: SearchQuery, _filters: SearchFilters) -> SearchFacetsResponse:
    return SearchFacetsResponse(
        cluster_roles={},
        provider={},
        result_types={},
        evidence_types={},
        has_face={"true": 0, "false": 0},
        has_authority_link={"true": 0, "false": 0},
    )
