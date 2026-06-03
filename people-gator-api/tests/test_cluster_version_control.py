import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.enums import ClusterRole, DeltaType, OperationType
from people_gator_api.db.ops import version_manager
from people_gator_api.schemas.clusters import (
    BranchOperationBody,
    ClusterSummary,
    MergeOperationBody,
    SourceVersionRef,
    SplitOperationBody,
    SplitTargetBody,
    StageOperationBody,
)
from people_gator_api.services import cluster_service


@dataclass
class FakeDelta:
    delta_id: uuid.UUID
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    delta_type: DeltaType
    weight: float


@dataclass
class FakeMember:
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    weight: float


@pytest.mark.asyncio
async def test_stage_cluster_advances_head_with_old_head_as_cas_expected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    cluster_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    old_head = uuid.uuid4()
    new_version_id = uuid.uuid4()
    op_id = uuid.uuid4()

    cluster = Cluster(cluster_id=cluster_id, head_version_id=old_head)
    advance_head = AsyncMock(return_value=True)
    monkeypatch.setattr(Cluster, "advance_head", advance_head)

    monkeypatch.setattr(version_manager, "_new_id", Mock(side_effect=[new_version_id, op_id]))
    monkeypatch.setattr(
        version_manager.Version,
        "get",
        AsyncMock(return_value=SimpleNamespace(cluster_role=ClusterRole.manual_cluster)),
    )
    monkeypatch.setattr(version_manager.Operation, "create_single", AsyncMock())
    monkeypatch.setattr(version_manager.Delta, "create", AsyncMock())
    monkeypatch.setattr(version_manager, "materialize_membership", AsyncMock())

    version = await version_manager.stage_cluster(
        session=session,
        cluster=cluster,
        actor_id=actor_id,
        new_role=None,
    )

    advance_head.assert_awaited_once_with(session, new_version_id, old_head)
    assert version.version_id == new_version_id


@pytest.mark.asyncio
async def test_stage_cluster_raises_on_concurrent_head_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    cluster_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    old_head = uuid.uuid4()

    cluster = Cluster(cluster_id=cluster_id, head_version_id=old_head)
    monkeypatch.setattr(Cluster, "advance_head", AsyncMock(return_value=False))

    monkeypatch.setattr(version_manager, "_new_id", Mock(side_effect=[uuid.uuid4(), uuid.uuid4()]))
    monkeypatch.setattr(
        version_manager.Version,
        "get",
        AsyncMock(return_value=SimpleNamespace(cluster_role=ClusterRole.manual_cluster)),
    )
    monkeypatch.setattr(version_manager.Operation, "create_single", AsyncMock())
    monkeypatch.setattr(version_manager.Delta, "create", AsyncMock())
    monkeypatch.setattr(version_manager, "materialize_membership", AsyncMock())

    with pytest.raises(RuntimeError, match="Concurrent write"):
        await version_manager.stage_cluster(
            session=session,
            cluster=cluster,
            actor_id=actor_id,
        )


@pytest.mark.asyncio
async def test_branch_cluster_does_not_update_cluster_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    cluster_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    source_version_id = uuid.uuid4()

    cluster = Cluster(cluster_id=cluster_id, head_version_id=source_version_id)
    monkeypatch.setattr(version_manager, "_new_id", Mock(side_effect=[uuid.uuid4(), uuid.uuid4()]))
    monkeypatch.setattr(
        version_manager.Version,
        "get",
        AsyncMock(return_value=SimpleNamespace(cluster_role=ClusterRole.grounded_cluster)),
    )
    create_single = AsyncMock()
    monkeypatch.setattr(version_manager.Operation, "create_single", create_single)

    branch_version = await version_manager.branch_cluster(
        session=session,
        cluster=cluster,
        actor_id=actor_id,
        from_version_id=source_version_id,
    )

    assert cluster.head_version_id == source_version_id
    assert branch_version.cluster_role == ClusterRole.grounded_cluster
    create_single.assert_awaited_once()


@pytest.mark.asyncio
async def test_merge_conflict_free_join_rejects_conflicting_memberships(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    actor_id = uuid.uuid4()

    source_cluster_a = uuid.uuid4()
    source_cluster_b = uuid.uuid4()
    source_version_a = uuid.uuid4()
    source_version_b = uuid.uuid4()

    conflict_evidence_id = uuid.uuid4()
    target_cluster = Cluster(cluster_id=uuid.uuid4(), head_version_id=source_version_a)

    monkeypatch.setattr(
        version_manager,
        "resolve_membership",
        AsyncMock(
            side_effect=[
                [
                    FakeMember(
                        evidence_id=conflict_evidence_id,
                        evidence_version_id=uuid.uuid4(),
                        weight=1.0,
                    )
                ],
                [],
            ]
        ),
    )

    with pytest.raises(version_manager.ConflictError) as exc:
        await version_manager.merge_clusters(
            session=session,
            source_versions=[
                (source_cluster_a, source_version_a),
                (source_cluster_b, source_version_b),
            ],
            target_cluster=target_cluster,
            actor_id=actor_id,
            operation_type=OperationType.conflict_free_join,
        )

    assert exc.value.evidence_ids == [conflict_evidence_id]


@pytest.mark.asyncio
async def test_resolve_pending_diff_keeps_latest_delta_per_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cluster_id = uuid.uuid4()
    version_id = uuid.uuid4()
    shared_evidence = uuid.uuid4()

    older = FakeDelta(
        delta_id=uuid.uuid4(),
        evidence_id=shared_evidence,
        evidence_version_id=uuid.uuid4(),
        delta_type=DeltaType.add,
        weight=0.4,
    )
    newer = FakeDelta(
        delta_id=uuid.uuid4(),
        evidence_id=shared_evidence,
        evidence_version_id=uuid.uuid4(),
        delta_type=DeltaType.remove,
        weight=1.0,
    )
    distinct = FakeDelta(
        delta_id=uuid.uuid4(),
        evidence_id=uuid.uuid4(),
        evidence_version_id=uuid.uuid4(),
        delta_type=DeltaType.add,
        weight=0.8,
    )

    monkeypatch.setattr(
        version_manager.Delta,
        "get_for_version",
        AsyncMock(return_value=[older, newer, distinct]),
    )

    session = Mock(spec=AsyncSession)
    pending = await version_manager.resolve_pending_diff(session, cluster_id, version_id)

    assert len(pending) == 2
    by_evidence = {item.evidence_id: item for item in pending}
    assert by_evidence[shared_evidence] is newer
    assert by_evidence[distinct.evidence_id] is distinct


@pytest.mark.asyncio
async def test_patch_cluster_head_returns_summary_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    cluster_id = uuid.uuid4()
    expected_head = uuid.uuid4()
    new_head = uuid.uuid4()

    cluster = SimpleNamespace(
        cluster_id=cluster_id,
        head_version_id=expected_head,
        advance_head=AsyncMock(return_value=True),
    )
    monkeypatch.setattr(cluster_service.Cluster, "get", AsyncMock(return_value=cluster))
    monkeypatch.setattr(
        cluster_service.Version,
        "get",
        AsyncMock(return_value=SimpleNamespace(cluster_role=ClusterRole.manual_cluster)),
    )

    summary = await cluster_service.patch_cluster_head(
        session=session,
        cluster_id=cluster_id,
        head_version_id=new_head,
        expected_head_version_id=expected_head,
    )

    assert summary == ClusterSummary(
        cluster_id=cluster_id,
        head_version_id=new_head,
        cluster_role=ClusterRole.manual_cluster,
    )


@pytest.mark.asyncio
async def test_execute_operation_stage_dispatches_to_stage_cluster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    cluster_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    staged_version_id = uuid.uuid4()

    cluster = SimpleNamespace(cluster_id=cluster_id, head_version_id=uuid.uuid4())
    monkeypatch.setattr(cluster_service.Cluster, "get", AsyncMock(return_value=cluster))
    monkeypatch.setattr(
        cluster_service,
        "stage_cluster",
        AsyncMock(return_value=SimpleNamespace(version_id=staged_version_id)),
    )

    result = await cluster_service.execute_operation(
        session=session,
        cluster_id=cluster_id,
        actor_id=actor_id,
        body=StageOperationBody(
            operation_type="stage",
            source_version_id=uuid.uuid4(),
            cluster_role=ClusterRole.saved_search,
        ),
    )

    assert result.version_id == staged_version_id


@pytest.mark.asyncio
async def test_execute_operation_split_returns_target_cluster_summaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    actor_id = uuid.uuid4()
    source_cluster_id = uuid.uuid4()

    source_cluster = SimpleNamespace(cluster_id=source_cluster_id, head_version_id=uuid.uuid4())
    monkeypatch.setattr(cluster_service.Cluster, "get", AsyncMock(return_value=source_cluster))

    split_cluster_a = SimpleNamespace(cluster_id=uuid.uuid4(), head_version_id=uuid.uuid4())
    split_cluster_b = SimpleNamespace(cluster_id=uuid.uuid4(), head_version_id=uuid.uuid4())

    monkeypatch.setattr(
        cluster_service,
        "split_cluster",
        AsyncMock(
            return_value=[
                (split_cluster_a, SimpleNamespace(version_id=split_cluster_a.head_version_id)),
                (split_cluster_b, SimpleNamespace(version_id=split_cluster_b.head_version_id)),
            ]
        ),
    )

    body = SplitOperationBody(
        operation_type="split",
        source_version_id=uuid.uuid4(),
        split_targets=[
            SplitTargetBody(cluster_role=ClusterRole.manual_cluster, evidence_ids=[uuid.uuid4()]),
            SplitTargetBody(cluster_role=ClusterRole.automatic_cluster, evidence_ids=[uuid.uuid4()]),
        ],
    )

    result = await cluster_service.execute_operation(
        session=session,
        cluster_id=source_cluster_id,
        actor_id=actor_id,
        body=body,
    )

    assert result.version_id is None
    assert [target.cluster_id for target in result.split_targets] == [
        split_cluster_a.cluster_id,
        split_cluster_b.cluster_id,
    ]
    assert [target.cluster_role for target in result.split_targets] == [
        ClusterRole.manual_cluster,
        ClusterRole.automatic_cluster,
    ]


@pytest.mark.asyncio
async def test_execute_operation_unsupported_body_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    actor_id = uuid.uuid4()
    cluster_id = uuid.uuid4()

    cluster = SimpleNamespace(cluster_id=cluster_id, head_version_id=uuid.uuid4())
    monkeypatch.setattr(cluster_service.Cluster, "get", AsyncMock(return_value=cluster))

    body = BranchOperationBody(
        operation_type="not-supported",
        source_version_id=uuid.uuid4(),
        cluster_role=ClusterRole.manual_cluster,
    )

    with pytest.raises(ValueError, match="unsupported_operation"):
        await cluster_service.execute_operation(
            session=session,
            cluster_id=cluster_id,
            actor_id=actor_id,
            body=body,
        )


@pytest.mark.asyncio
async def test_execute_operation_merge_dispatches_with_source_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = Mock(spec=AsyncSession)
    actor_id = uuid.uuid4()
    cluster_id = uuid.uuid4()
    expected_version = uuid.uuid4()

    cluster = SimpleNamespace(cluster_id=cluster_id, head_version_id=uuid.uuid4())
    monkeypatch.setattr(cluster_service.Cluster, "get", AsyncMock(return_value=cluster))
    merge_mock = AsyncMock(return_value=SimpleNamespace(version_id=expected_version))
    monkeypatch.setattr(cluster_service, "merge_clusters", merge_mock)

    source_a_cluster = uuid.uuid4()
    source_a_version = uuid.uuid4()
    source_b_cluster = uuid.uuid4()
    source_b_version = uuid.uuid4()

    body = MergeOperationBody(
        operation_type="union",
        source_versions=[
            SourceVersionRef(cluster_id=source_a_cluster, version_id=source_a_version),
            SourceVersionRef(cluster_id=source_b_cluster, version_id=source_b_version),
        ],
        cluster_role=ClusterRole.grounded_cluster,
    )

    result = await cluster_service.execute_operation(
        session=session,
        cluster_id=cluster_id,
        actor_id=actor_id,
        body=body,
    )

    assert result.version_id == expected_version
    merge_mock.assert_awaited_once()
