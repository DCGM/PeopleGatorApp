import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import EvidenceType, PrincipalType, RegistrySource
from people_gator_api.db.models.principal import ModelAgent, ServiceAgent
from people_gator_api.db.models.search_profile import SearchProfile, SearchProfileModality
from people_gator_api.schemas.principals import ModelAgentCreateRequest, ServiceAgentCreateRequest
from people_gator_api.schemas.search import (
    SearchFilters,
    SearchProfileCloneRequest,
    SearchProfileCreateRequest,
    SearchProfileModalityIn,
    SearchQuery,
    SearchRequest,
)
from people_gator_api.services import principal_service, search_service


@dataclass
class FakeScalarResult[T]:
    items: list[T]

    def all(self) -> list[T]:
        return self.items


@dataclass
class FakeExecuteResult[T]:
    items: list[T]

    def scalars(self) -> FakeScalarResult[T]:
        return FakeScalarResult(self.items)


@pytest.mark.asyncio
async def test_create_service_agent_maps_created_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)

    agent = ServiceAgent(
        principal_id=uuid.uuid4(),
        principal_type=PrincipalType.service_agent,
        display_name="Importer",
        is_active=True,
        agent_slug="system:importer",
        description="source ingest",
    )
    monkeypatch.setattr(principal_service.ServiceAgent, "get_or_create", AsyncMock(return_value=(agent, True)))

    payload = ServiceAgentCreateRequest(
        agent_slug="system:importer",
        display_name="Importer",
        description="source ingest",
    )

    response = await principal_service.create_service_agent(session, payload)

    assert response.principal_id == agent.principal_id
    assert response.principal_type == PrincipalType.service_agent


@pytest.mark.asyncio
async def test_create_model_agent_creates_new_when_slot_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()

    monkeypatch.setattr(principal_service.ModelAgent, "get_by_slot", AsyncMock(return_value=None))

    payload = ModelAgentCreateRequest(
        display_name="FaceNet V1",
        evidence_type=EvidenceType.face_detection,
        role="face",
        model_slug="facenet-v1",
        model_version="1.0.0",
        registry_source=RegistrySource.local,
        registry_uri="file:///models/facenet-v1",
        is_active=True,
    )

    response = await principal_service.create_model_agent(session, payload)

    assert response.principal_type == PrincipalType.model_agent
    assert response.display_name == "FaceNet V1"
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_create_model_agent_reuses_existing_and_updates_active(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()

    existing = ModelAgent(
        principal_id=uuid.uuid4(),
        principal_type=PrincipalType.model_agent,
        display_name="NER V1",
        is_active=True,
        evidence_type=EvidenceType.named_entity,
        role="text",
        model_slug="ner-v1",
        model_version="1.0.0",
        registry_source=RegistrySource.mlflow,
        registry_uri="mlflow://ner-v1/1.0.0",
    )

    monkeypatch.setattr(principal_service.ModelAgent, "get_by_slot", AsyncMock(return_value=existing))

    payload = ModelAgentCreateRequest(
        display_name="NER V1",
        evidence_type=EvidenceType.named_entity,
        role="text",
        model_slug="ner-v1",
        model_version="1.0.0",
        registry_source=RegistrySource.mlflow,
        registry_uri="mlflow://ner-v1/1.0.0",
        is_active=False,
    )

    response = await principal_service.create_model_agent(session, payload)

    assert response.principal_id == existing.principal_id
    assert response.is_active is False
    assert existing.is_active is False


@pytest.mark.asyncio
async def test_list_profiles_filters_owner_system_and_public(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    owner_id = uuid.uuid4()

    owned = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name="mine",
        description=None,
        owner_id=owner_id,
        is_public=False,
        is_system=False,
    )
    owned.modalities = []

    system = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name="system",
        description=None,
        owner_id=None,
        is_public=False,
        is_system=True,
    )
    system.modalities = []

    public = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name="public",
        description=None,
        owner_id=uuid.uuid4(),
        is_public=True,
        is_system=False,
    )
    public.modalities = []

    private_other = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name="private-other",
        description=None,
        owner_id=uuid.uuid4(),
        is_public=False,
        is_system=False,
    )
    private_other.modalities = []

    session.execute = AsyncMock(return_value=FakeExecuteResult([owned, system, public, private_other]))

    result = await search_service.list_profiles(
        session=session,
        principal_id=owner_id,
        include_system=True,
        include_public=True,
    )

    names = {item.profile_name for item in result}
    assert names == {"mine", "system", "public"}


@pytest.mark.asyncio
async def test_search_without_save_does_not_create_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    monkeypatch.setattr(search_service.Cluster, "create", AsyncMock())
    monkeypatch.setattr(search_service.Version, "create", AsyncMock())

    request = SearchRequest(
        query=SearchQuery(names=["Ada"], texts=None, evidence_ids=None, reference_cluster_id=None),
        profile_id=None,
        result_types=["cluster", "evidence"],
        filters=SearchFilters(),
        limit=10,
        after_id=None,
        save=False,
    )

    response = await search_service.search(session, request)

    assert response.search_cluster_id is None
    assert response.total == 0
    assert "saved_search" in response.facets["cluster_roles"]


@pytest.mark.asyncio
async def test_search_with_save_creates_saved_search_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)

    cluster_id = uuid.uuid4()
    version_id = uuid.uuid4()

    cluster = Mock()
    cluster.cluster_id = cluster_id
    cluster.head_version_id = None

    version = Mock()
    version.version_id = version_id

    monkeypatch.setattr(search_service.Cluster, "create", AsyncMock(return_value=cluster))
    monkeypatch.setattr(search_service.Version, "create", AsyncMock(return_value=version))

    request = SearchRequest(
        query=SearchQuery(names=None, texts=["historian"], evidence_ids=None, reference_cluster_id=None),
        profile_id=uuid.uuid4(),
        result_types=["cluster"],
        filters=SearchFilters(),
        limit=5,
        after_id=None,
        save=True,
    )

    response = await search_service.search(session, request)

    assert response.search_cluster_id == cluster_id
    assert cluster.head_version_id == version_id


@pytest.mark.asyncio
async def test_clone_profile_uses_fallback_clone_name(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    source = SearchProfile(
        profile_id=uuid.uuid4(),
        profile_name="base-profile",
        description="base",
        owner_id=uuid.uuid4(),
        is_public=True,
        is_system=False,
    )
    source.modalities = [
        SearchProfileModality(
            profile_id=source.profile_id,
            evidence_type=EvidenceType.face_detection,
            weight=1.0,
            model_id=None,
            enabled=True,
            min_confidence=0.8,
        )
    ]

    session.scalar = AsyncMock(return_value=source)

    cloned = await search_service.clone_profile(
        session=session,
        profile_id=source.profile_id,
        owner_id=uuid.uuid4(),
        request=SearchProfileCloneRequest(profile_name=None),
    )

    assert cloned is not None
    assert cloned.profile_name == "base-profile-clone"


@pytest.mark.asyncio
async def test_create_profile_sets_owner_and_adds_modalities() -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    owner_id = uuid.uuid4()

    request = SearchProfileCreateRequest(
        profile_name="annotator-default",
        description="annotator profile",
        is_public=False,
        modalities=[
            SearchProfileModalityIn(
                evidence_type=EvidenceType.face_detection,
                weight=0.7,
                model_id=None,
                enabled=True,
                min_confidence=0.5,
            ),
            SearchProfileModalityIn(
                evidence_type=EvidenceType.named_entity,
                weight=0.3,
                model_id=None,
                enabled=True,
                min_confidence=None,
            ),
        ],
    )

    response = await search_service.create_profile(session, owner_id=owner_id, request=request)

    assert response.owner_id == owner_id
    assert response.profile_name == "annotator-default"
    assert session.add.call_count == 3
