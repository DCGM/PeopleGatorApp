import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import (
    EvidenceType,
    ProcessingStatus,
    ProviderType,
    TaskRole,
    TaskStatus,
)
from people_gator_api.db.models.evidence import Evidence
from people_gator_api.db.models.source import Source
from people_gator_api.db.models.source_processing import SourceProcessing
from people_gator_api.db.models.task import Task
from people_gator_api.schemas.evidence import AuthorityEvidenceIngestRequest, DerivedEvidenceIngestRequest
from people_gator_api.schemas.sources import SourceCreateRequest
from people_gator_api.services import evidence_service, source_service, task_service


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
async def test_create_source_returns_existing_when_content_hash_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    source_id = uuid.uuid4()

    existing = Source(
        source_id=source_id,
        source="doc-1",
        source_schema_name="schema-a",
        provider=ProviderType.local,
        metadata_={"page": 1},
        content_hash="abc123",
        created_by=uuid.uuid4(),
    )
    monkeypatch.setattr(source_service.Source, "get_by_content_hash", AsyncMock(return_value=existing))
    monkeypatch.setattr(source_service.Source, "create", AsyncMock())

    payload = SourceCreateRequest(
        source_schema_name="schema-a",
        source="doc-1",
        provider=ProviderType.local,
        content_hash="abc123",
        metadata={"page": 1},
    )

    response, created = await source_service.create_source(session, payload, created_by=uuid.uuid4())

    assert created is False
    assert response.source_id == source_id


@pytest.mark.asyncio
async def test_create_source_creates_new_when_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    source_id = uuid.uuid4()
    creator = uuid.uuid4()

    created_source = Source(
        source_id=source_id,
        source="doc-2",
        source_schema_name="schema-b",
        provider=ProviderType.kramerius,
        metadata_={"collection": "x"},
        content_hash="hash-new",
        created_by=creator,
    )

    monkeypatch.setattr(source_service.Source, "get_by_content_hash", AsyncMock(return_value=None))
    create_mock = AsyncMock(return_value=created_source)
    monkeypatch.setattr(source_service.Source, "create", create_mock)

    payload = SourceCreateRequest(
        source_schema_name="schema-b",
        source="doc-2",
        provider=ProviderType.kramerius,
        content_hash="hash-new",
        metadata={"collection": "x"},
    )

    response, created = await source_service.create_source(session, payload, created_by=creator)

    assert created is True
    assert response.source_id == source_id
    create_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_source_processing_sets_started_and_completed_timestamps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()

    row = SourceProcessing(
        source_id=uuid.uuid4(),
        producer_id=uuid.uuid4(),
        processing_status=ProcessingStatus.queued,
        started_at=None,
        completed_at=None,
        error_message=None,
    )

    monkeypatch.setattr(source_service.SourceProcessing, "get", AsyncMock(return_value=row))
    monkeypatch.setattr(source_service.SourceProcessing, "create", AsyncMock())

    updated = await source_service.upsert_source_processing(
        session=session,
        source_id=row.source_id,
        producer_id=row.producer_id,
        processing_status=ProcessingStatus.in_progress,
        error_message=None,
    )

    assert updated.processing_status == ProcessingStatus.in_progress
    assert updated.started_at is not None

    updated = await source_service.upsert_source_processing(
        session=session,
        source_id=row.source_id,
        producer_id=row.producer_id,
        processing_status=ProcessingStatus.complete,
        error_message=None,
    )

    assert updated.processing_status == ProcessingStatus.complete
    assert updated.completed_at is not None


@pytest.mark.asyncio
async def test_get_source_processing_formats_datetimes_as_iso_strings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    source_id = uuid.uuid4()

    row = SourceProcessing(
        source_id=source_id,
        producer_id=uuid.uuid4(),
        processing_status=ProcessingStatus.failed,
        started_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        error_message="boom",
    )

    monkeypatch.setattr(source_service.SourceProcessing, "list_for_source", AsyncMock(return_value=[row]))

    response = await source_service.get_source_processing(session, source_id)

    assert response.source_id == source_id
    assert response.processing[0].started_at == "2026-01-01T12:00:00+00:00"
    assert response.processing[0].completed_at == "2026-01-01T12:05:00+00:00"


@pytest.mark.asyncio
async def test_ingest_derived_returns_unchanged_for_same_content_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)

    evidence_id = uuid.uuid4()
    existing = Evidence(
        evidence_id=evidence_id,
        evidence_version_id=uuid.uuid4(),
        evidence_type=EvidenceType.face_detection,
        schema_version="v1",
        source_id=uuid.uuid4(),
        source_path="p1",
        content_hash="same-hash",
        is_deleted=False,
        is_stale=False,
    )
    monkeypatch.setattr(evidence_service.Evidence, "get", AsyncMock(return_value=existing))

    payload = DerivedEvidenceIngestRequest(
        evidence_id=evidence_id,
        source_id=existing.source_id,
        source_path="p1",
        evidence_type=EvidenceType.face_detection,
        schema_version="v1",
        producer_id=uuid.uuid4(),
        content_hash="same-hash",
        produced_metadata={"confidence": 0.9},
    )

    result = await evidence_service.ingest_derived(session, payload)

    assert result.status == "unchanged"
    assert result.evidence_id == existing.evidence_id


@pytest.mark.asyncio
async def test_ingest_derived_creates_base_and_derived_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()

    monkeypatch.setattr(evidence_service.Evidence, "get", AsyncMock(return_value=None))

    payload = DerivedEvidenceIngestRequest(
        evidence_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        source_path="p1",
        evidence_type=EvidenceType.face_detection,
        schema_version="v1",
        producer_id=uuid.uuid4(),
        content_hash="face-1",
        produced_metadata={"confidence": 0.9},
    )

    result = await evidence_service.ingest_derived(session, payload)

    assert result.status == "created"
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_ingest_authority_creates_base_and_authority_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    session.add = Mock()

    monkeypatch.setattr(evidence_service.Evidence, "get", AsyncMock(return_value=None))

    payload = AuthorityEvidenceIngestRequest(
        evidence_id=uuid.uuid4(),
        source_id=uuid.uuid4(),
        source_path=None,
        evidence_type=EvidenceType.grounded_name,
        schema_version="v1",
        producer_id=uuid.uuid4(),
        content_hash="auth-1",
        metadata={"name": "Ada"},
    )

    result = await evidence_service.ingest_authority(session, payload)

    assert result.status == "created"
    assert session.add.call_count == 2


@pytest.mark.asyncio
async def test_list_tasks_maps_model_rows_to_schema_responses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)

    task = Task(
        task_id=uuid.uuid4(),
        cluster_id=uuid.uuid4(),
        pinned_version_id=uuid.uuid4(),
        head_version_id=uuid.uuid4(),
        assignee_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        task_role=TaskRole.annotate,
        status=TaskStatus.pending,
    )

    session.execute = AsyncMock(return_value=FakeExecuteResult([task]))

    responses = await task_service.list_tasks(
        session=session,
        assignee_id=None,
        task_role=None,
        status=None,
        cluster_id=None,
        after_id=None,
        limit=50,
    )

    assert len(responses) == 1
    assert responses[0].task_id == task.task_id
    assert responses[0].task_role == TaskRole.annotate


@pytest.mark.asyncio
async def test_get_task_returns_none_for_missing_task(monkeypatch: pytest.MonkeyPatch) -> None:
    session = Mock(spec=AsyncSession)
    monkeypatch.setattr(task_service.Task, "get", AsyncMock(return_value=None))

    result = await task_service.get_task(session, uuid.uuid4())

    assert result is None
