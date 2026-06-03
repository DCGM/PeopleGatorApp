import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.delta import Delta
from people_gator_api.db.models.enums import ClusterRole, DeltaType, OperationType
from people_gator_api.db.models.membership import Membership
from people_gator_api.db.models.operation import Operation
from people_gator_api.db.models.version import Version
from people_gator_api.db.ops.version_manager import (
    EvidenceRef,
    branch_cluster,
    initialize_cluster,
    merge_clusters,
    resolve_pending_diff,
    split_cluster,
    stage_cluster,
)
from people_gator_api.schemas.clusters import (
    BranchOperationBody,
    ClusterSummary,
    DeltaWriteRequest,
    MembershipItem,
    MembershipResponse,
    MergeOperationBody,
    OperationResult,
    SplitOperationBody,
    StageOperationBody,
    VersionSummary,
)


async def list_clusters(
    session: AsyncSession,
    cluster_roles: list[ClusterRole],
    after_id: uuid.UUID | None,
    limit: int,
) -> list[ClusterSummary]:
    stmt = sa.select(Cluster).order_by(Cluster.cluster_id.asc()).limit(limit)
    if after_id is not None:
        stmt = stmt.where(Cluster.cluster_id > after_id)
    if cluster_roles:
        stmt = stmt.join(Version, Version.version_id == Cluster.head_version_id).where(
            Version.cluster_role.in_(cluster_roles)
        )
    result = await session.execute(stmt)
    clusters = list(result.scalars().all())

    return [
        ClusterSummary(
            cluster_id=cluster.cluster_id,
            head_version_id=cluster.head_version_id,
            cluster_role=None,
        )
        for cluster in clusters
    ]


async def get_cluster_summary(session: AsyncSession, cluster_id: uuid.UUID) -> ClusterSummary | None:
    cluster = await Cluster.get(session, cluster_id)
    if cluster is None:
        return None

    role: ClusterRole | None = None
    if cluster.head_version_id is not None:
        head = await Version.get(session, cluster.head_version_id)
        role = head.cluster_role if head is not None else None

    return ClusterSummary(
        cluster_id=cluster.cluster_id,
        head_version_id=cluster.head_version_id,
        cluster_role=role,
    )


async def patch_cluster_head(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    head_version_id: uuid.UUID,
    expected_head_version_id: uuid.UUID,
) -> ClusterSummary | None:
    cluster = await Cluster.get(session, cluster_id)
    if cluster is None:
        return None
    advanced = await cluster.advance_head(session, head_version_id, expected_head_version_id)
    if not advanced:
        return None
    role: ClusterRole | None = None
    head = await Version.get(session, head_version_id)
    if head is not None:
        role = head.cluster_role
    return ClusterSummary(
        cluster_id=cluster.cluster_id,
        head_version_id=head_version_id,
        cluster_role=role,
    )


async def create_manual_cluster(
    session: AsyncSession,
    actor_id: uuid.UUID,
    role: ClusterRole,
) -> ClusterSummary:
    cluster, version = await initialize_cluster(
        session=session,
        cluster_role=role,
        actor_id=actor_id,
    )
    return ClusterSummary(cluster_id=cluster.cluster_id, head_version_id=version.version_id, cluster_role=role)


async def get_membership(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID | None,
) -> MembershipResponse:
    memberships = await Membership.get_for_cluster(session, cluster_id)
    as_of = version_id
    if as_of is None and memberships:
        as_of = memberships[0].as_of_version_id

    return MembershipResponse(
        cluster_id=cluster_id,
        version_id=version_id,
        members=[
            MembershipItem(
                evidence_id=item.evidence_id,
                evidence_version_id=item.evidence_version_id,
                weight=item.weight,
                as_of_version_id=item.as_of_version_id,
            )
            for item in memberships
        ],
    )


async def write_delta(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
    actor_id: uuid.UUID,
    payload: DeltaWriteRequest,
) -> Delta:
    delta_type = DeltaType(payload.delta_type)
    return await Delta.create(
        session=session,
        cluster_id=cluster_id,
        version_id=version_id,
        evidence_id=payload.evidence_id,
        evidence_version_id=payload.evidence_version_id,
        delta_type=delta_type,
        actor_id=actor_id,
        weight=payload.weight or 1.0,
    )


async def get_versions(session: AsyncSession, cluster_id: uuid.UUID) -> list[VersionSummary]:
    versions = await Version.get_for_cluster(session, cluster_id)
    return [
        VersionSummary(
            version_id=version.version_id,
            cluster_id=version.cluster_id,
            cluster_role=version.cluster_role,
            actor_id=version.actor_id,
            search_profile_id=version.search_profile_id,
        )
        for version in versions
    ]


async def execute_operation(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    actor_id: uuid.UUID,
    body: StageOperationBody | BranchOperationBody | MergeOperationBody | SplitOperationBody,
) -> OperationResult:
    cluster = await Cluster.get(session, cluster_id)
    if cluster is None:
        raise LookupError("cluster_not_found")

    if isinstance(body, StageOperationBody) and body.operation_type == "stage":
        version = await stage_cluster(
            session=session,
            cluster=cluster,
            actor_id=actor_id,
            new_role=body.cluster_role,
        )
        return OperationResult(operation_id=None, version_id=version.version_id)

    if isinstance(body, BranchOperationBody) and body.operation_type == "branch":
        version = await branch_cluster(
            session=session,
            cluster=cluster,
            actor_id=actor_id,
            from_version_id=body.source_version_id,
        )
        return OperationResult(operation_id=None, version_id=version.version_id)

    if isinstance(body, MergeOperationBody):
        op_type = OperationType(body.operation_type)
        version = await merge_clusters(
            session=session,
            source_versions=[(item.cluster_id, item.version_id) for item in body.source_versions],
            target_cluster=cluster,
            actor_id=actor_id,
            operation_type=op_type,
            new_role=body.cluster_role,
        )
        return OperationResult(operation_id=None, version_id=version.version_id)

    if isinstance(body, SplitOperationBody) and body.operation_type == "split":
        split_result = await split_cluster(
            session=session,
            source_cluster=cluster,
            actor_id=actor_id,
            source_version_id=body.source_version_id,
            new_cluster_memberships=[
                (
                    target.cluster_role,
                    [EvidenceRef(evidence_id=eid, evidence_version_id=eid, weight=1.0) for eid in target.evidence_ids],
                )
                for target in body.split_targets
            ],
        )
        return OperationResult(
            operation_id=None,
            version_id=None,
            split_targets=[
                ClusterSummary(
                    cluster_id=item_cluster.cluster_id,
                    head_version_id=item_cluster.head_version_id,
                    cluster_role=target_role,
                )
                for (item_cluster, _), target_role in zip(
                    split_result,
                    [target.cluster_role for target in body.split_targets],
                    strict=False,
                )
            ],
        )

    raise ValueError("unsupported_operation")


async def list_pending_deltas(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[Delta]:
    return await resolve_pending_diff(session, cluster_id, version_id)


async def list_version_operations(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> tuple[list[OperationType], list[OperationType]]:
    incoming = await Operation.get_ancestors_of(session, cluster_id, version_id)
    outgoing = await Operation.get_outgoing_from(session, cluster_id, version_id)
    return ([item.operation_type for item in incoming], [item.operation_type for item in outgoing])
