"""Version manager — high-level multi-step DB operations for the cluster/version
graph defined in the product spec.

All public functions accept an ``AsyncSession`` and must be called inside an
active transaction (the caller is responsible for commit / rollback).

Algorithms implemented:
  - initialize_cluster        spec §4.5 empty operation
  - stage_cluster             spec §4.5 stage operation (advance head)
  - branch_cluster            spec §4.5 branch operation
  - merge_clusters            spec §4.5 union / intersection / conflict_free_join
  - split_cluster             spec §4.5 split operation
  - resolve_membership        spec §4.8.1 DAG walk membership resolution
  - resolve_pending_diff      spec §4.8.2 pending diff for a working version
  - materialize_membership    persist resolved state to MEMBERSHIP
  - apply_delta_to_membership incremental MEMBERSHIP update on single DELTA
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.delta import Delta
from people_gator_api.db.models.enums import ClusterRole, DeltaType, OperationType
from people_gator_api.db.models.membership import Membership
from people_gator_api.db.models.operation import Operation
from people_gator_api.db.models.version import Version

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data-transfer types
# ---------------------------------------------------------------------------


@dataclass
class EvidenceRef:
    """Minimal reference to a specific evidence version with association weight."""

    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    weight: float = 1.0


@dataclass
class ResolvedMember:
    """One entry in a resolved cluster membership snapshot."""

    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    weight: float


# ---------------------------------------------------------------------------
# High-level versioning operations
# ---------------------------------------------------------------------------


async def initialize_cluster(
    session: AsyncSession,
    cluster_role: ClusterRole,
    actor_id: uuid.UUID,
    initial_evidence: list[EvidenceRef] | None = None,
    search_profile_id: uuid.UUID | None = None,
) -> tuple[Cluster, Version]:
    """Create a brand-new cluster with its initial version.

    Atomically:
    1. Creates CLUSTER (no head yet).
    2. Creates the initial VERSION authored by ``actor_id``.
    3. Creates an ``empty`` OPERATION row.
    4. Creates DELTA(add) rows for each item in ``initial_evidence``.
    5. Updates CLUSTER.head_version_id.
    6. Materializes MEMBERSHIP.

    Returns ``(cluster, version)``.
    """
    cluster = Cluster(cluster_id=_new_id())
    session.add(cluster)

    version = Version(
        version_id=_new_id(),
        cluster_id=cluster.cluster_id,
        cluster_role=cluster_role,
        actor_id=actor_id,
        search_profile_id=search_profile_id,
    )
    session.add(version)

    op_id = _new_id()
    await Operation.create_single(
        session,
        operation_id=op_id,
        operation_type=OperationType.empty,
        target_cluster_id=cluster.cluster_id,
        target_version_id=version.version_id,
        source_cluster_id=None,
        source_version_id=None,
    )

    for ref in initial_evidence or []:
        await Delta.create(
            session,
            cluster_id=cluster.cluster_id,
            version_id=version.version_id,
            evidence_id=ref.evidence_id,
            evidence_version_id=ref.evidence_version_id,
            delta_type=DeltaType.add,
            actor_id=actor_id,
            weight=ref.weight,
        )

    cluster.head_version_id = version.version_id
    await materialize_membership(session, cluster, version.version_id)

    logger.info(
        "Initialized cluster %s version %s role=%s",
        cluster.cluster_id, version.version_id, cluster_role.value,
    )
    return cluster, version


async def stage_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    added_evidence: list[EvidenceRef] | None = None,
    removed_evidence: list[EvidenceRef] | None = None,
    new_role: ClusterRole | None = None,
    search_profile_id: uuid.UUID | None = None,
) -> Version:
    """Advance a cluster to a new VERSION via a ``stage`` operation.

    Atomically:
    1. Creates a new VERSION authored by ``actor_id``.
    2. Creates a ``stage`` OPERATION from the current head.
    3. Creates DELTA rows for all adds and removes.
    4. Updates CLUSTER.head_version_id.
    5. Re-materializes MEMBERSHIP.

    Returns the new VERSION.
    """
    if cluster.head_version_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head version — use initialize_cluster first."
        )

    old_head = cluster.head_version_id
    role = new_role or ClusterRole.manual_cluster  # caller-supplied role wins

    # Read current role from head version if not supplied.
    if new_role is None:
        head_version = await Version.get(session, old_head)
        if head_version is not None:
            role = head_version.cluster_role

    new_version = Version(
        version_id=_new_id(),
        cluster_id=cluster.cluster_id,
        cluster_role=role,
        actor_id=actor_id,
        search_profile_id=search_profile_id,
    )
    session.add(new_version)

    op_id = _new_id()
    await Operation.create_single(
        session,
        operation_id=op_id,
        operation_type=OperationType.stage,
        source_cluster_id=cluster.cluster_id,
        source_version_id=old_head,
        target_cluster_id=cluster.cluster_id,
        target_version_id=new_version.version_id,
    )

    for ref in added_evidence or []:
        await Delta.create(
            session,
            cluster_id=cluster.cluster_id,
            version_id=new_version.version_id,
            evidence_id=ref.evidence_id,
            evidence_version_id=ref.evidence_version_id,
            delta_type=DeltaType.add,
            actor_id=actor_id,
            weight=ref.weight,
        )

    for ref in removed_evidence or []:
        await Delta.create(
            session,
            cluster_id=cluster.cluster_id,
            version_id=new_version.version_id,
            evidence_id=ref.evidence_id,
            evidence_version_id=ref.evidence_version_id,
            delta_type=DeltaType.remove,
            actor_id=actor_id,
            weight=ref.weight,
        )

    # CAS advance head — conditioned on current head == old_head.
    advanced = await cluster.advance_head(session, new_version.version_id, old_head)
    if not advanced:
        raise RuntimeError(
            f"Concurrent write on cluster {cluster.cluster_id}: head_version_id changed since read — retry after re-reading."
        )

    await materialize_membership(session, cluster, new_version.version_id)

    logger.info(
        "Staged cluster %s: %s -> %s",
        cluster.cluster_id, old_head, new_version.version_id,
    )
    return new_version


async def branch_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    from_version_id: uuid.UUID | None = None,
) -> Version:
    """Create a branch VERSION off a given (or head) version.

    ``CLUSTER.head_version_id`` is NOT updated per spec §4.5.

    Returns the new branch VERSION.
    """
    source_version_id = from_version_id or cluster.head_version_id
    if source_version_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head version and no from_version_id was provided."
        )

    # Inherit role from the source version.
    source_version = await Version.get(session, source_version_id)
    role = source_version.cluster_role if source_version is not None else ClusterRole.manual_cluster

    branch_version = Version(
        version_id=_new_id(),
        cluster_id=cluster.cluster_id,
        cluster_role=role,
        actor_id=actor_id,
    )
    session.add(branch_version)

    op_id = _new_id()
    await Operation.create_single(
        session,
        operation_id=op_id,
        operation_type=OperationType.branch,
        source_cluster_id=cluster.cluster_id,
        source_version_id=source_version_id,
        target_cluster_id=cluster.cluster_id,
        target_version_id=branch_version.version_id,
    )

    logger.info(
        "Branched cluster %s from version %s -> %s",
        cluster.cluster_id, source_version_id, branch_version.version_id,
    )
    return branch_version


async def merge_clusters(
    session: AsyncSession,
    source_versions: list[tuple[uuid.UUID, uuid.UUID]],
    target_cluster: Cluster,
    actor_id: uuid.UUID,
    operation_type: OperationType,
    new_role: ClusterRole | None = None,
    extra_add: list[EvidenceRef] | None = None,
    extra_remove: list[EvidenceRef] | None = None,
) -> Version:
    """Merge one or more source versions into a new target VERSION.

    ``source_versions`` is a list of ``(cluster_id, version_id)`` pairs.
    ``operation_type`` must be ``union``, ``intersection``, or
    ``conflict_free_join``.

    For ``conflict_free_join`` this function performs the conflict check and
    raises ``ConflictError`` listing conflicting evidence_ids before writing
    anything.

    Atomically:
    1. [conflict_free_join only] checks for conflicts.
    2. Creates the target VERSION.
    3. Creates one OPERATION row per source version.
    4. Writes caller-supplied extra DELTA rows.
    5. Updates CLUSTER.head_version_id (CAS).
    6. Re-materializes MEMBERSHIP.

    Returns the new target VERSION.
    """
    if operation_type not in (
        OperationType.union,
        OperationType.intersection,
        OperationType.conflict_free_join,
    ):
        raise ValueError(f"operation_type must be union/intersection/conflict_free_join, got {operation_type}")

    # Resolve memberships for all sources to determine result membership.
    source_memberships: list[dict[uuid.UUID, ResolvedMember]] = []
    for src_cluster_id, src_version_id in source_versions:
        resolved = await resolve_membership(session, src_cluster_id, src_version_id)
        source_memberships.append({m.evidence_id: m for m in resolved})

    if operation_type == OperationType.conflict_free_join:
        # Detect conflicts: evidence present in some sources as add, removed in others.
        all_ids: set[uuid.UUID] = {eid for sm in source_memberships for eid in sm}
        conflicts: list[uuid.UUID] = []
        for eid in all_ids:
            present_in = [eid in sm for sm in source_memberships]
            if any(present_in) and not all(present_in):
                conflicts.append(eid)
        if conflicts:
            raise ConflictError(conflicts)

    # Compute the new membership depending on operation type.
    if operation_type in (OperationType.union, OperationType.conflict_free_join):
        result_members: dict[uuid.UUID, ResolvedMember] = {}
        for sm in source_memberships:
            for eid, member in sm.items():
                if eid not in result_members or member.weight > result_members[eid].weight:
                    result_members[eid] = member
    else:  # intersection
        if not source_memberships:
            result_members = {}
        else:
            common_ids = set(source_memberships[0].keys())
            for sm in source_memberships[1:]:
                common_ids &= sm.keys()
            result_members = {
                eid: source_memberships[0][eid] for eid in common_ids
            }

    # Current role fallback.
    role = new_role
    if role is None and target_cluster.head_version_id is not None:
        head_v = await Version.get(session, target_cluster.head_version_id)
        role = head_v.cluster_role if head_v is not None else ClusterRole.manual_cluster
    if role is None:
        role = ClusterRole.manual_cluster

    merge_version = Version(
        version_id=_new_id(),
        cluster_id=target_cluster.cluster_id,
        cluster_role=role,
        actor_id=actor_id,
    )
    session.add(merge_version)

    op_id = _new_id()
    for src_cluster_id, src_version_id in source_versions:
        await Operation.create_single(
            session,
            operation_id=op_id,
            operation_type=operation_type,
            source_cluster_id=src_cluster_id,
            source_version_id=src_version_id,
            target_cluster_id=target_cluster.cluster_id,
            target_version_id=merge_version.version_id,
        )

    for ref in extra_add or []:
        await Delta.create(
            session,
            cluster_id=target_cluster.cluster_id,
            version_id=merge_version.version_id,
            evidence_id=ref.evidence_id,
            evidence_version_id=ref.evidence_version_id,
            delta_type=DeltaType.add,
            actor_id=actor_id,
            weight=ref.weight,
        )
    for ref in extra_remove or []:
        await Delta.create(
            session,
            cluster_id=target_cluster.cluster_id,
            version_id=merge_version.version_id,
            evidence_id=ref.evidence_id,
            evidence_version_id=ref.evidence_version_id,
            delta_type=DeltaType.remove,
            actor_id=actor_id,
            weight=ref.weight,
        )

    # The caller is responsible for explicitly setting head_version_id for
    # merge operations (reviewer decides); we do it here only if the current
    # head is among the sources.
    source_version_ids = {vid for _, vid in source_versions}
    if target_cluster.head_version_id in source_version_ids:
        old_head = target_cluster.head_version_id
        assert old_head is not None  # narrowing
        await target_cluster.advance_head(session, old_head, merge_version.version_id)

    await materialize_membership(session, target_cluster, merge_version.version_id)

    logger.info(
        "Merged %d source versions into cluster %s version %s (op=%s)",
        len(source_versions), target_cluster.cluster_id, merge_version.version_id, operation_type.value,
    )
    return merge_version


async def split_cluster(
    session: AsyncSession,
    source_cluster: Cluster,
    actor_id: uuid.UUID,
    source_version_id: uuid.UUID | None = None,
    new_cluster_memberships: list[tuple[ClusterRole, list[EvidenceRef]]] | None = None,
) -> list[tuple[Cluster, Version]]:
    """Split a cluster into two or more new clusters.

    ``new_cluster_memberships`` is a list of ``(role, evidence_refs)`` tuples,
    one per split target.

    Atomically:
    1. For each target: creates a new CLUSTER + VERSION + ``empty`` OPERATION.
    2. Creates one ``split`` OPERATION row per target (all sharing one op_id).
    3. Creates DELTA(add) rows for each target's initial evidence.
    4. Updates each new CLUSTER.head_version_id.
    5. Materializes MEMBERSHIP for each new cluster.

    Returns a list of ``(cluster, version)`` for each split target.
    """
    src_version_id = source_version_id or source_cluster.head_version_id
    if src_version_id is None:
        raise ValueError(
            f"Cluster {source_cluster.cluster_id} has no head version and no source_version_id was provided."
        )

    op_id = _new_id()
    results: list[tuple[Cluster, Version]] = []

    for role, evidence_refs in (new_cluster_memberships or []):
        new_cluster = Cluster(cluster_id=_new_id())
        session.add(new_cluster)

        new_version = Version(
            version_id=_new_id(),
            cluster_id=new_cluster.cluster_id,
            cluster_role=role,
            actor_id=actor_id,
        )
        session.add(new_version)

        # empty bootstrap for the new cluster.
        await Operation.create_single(
            session,
            operation_id=_new_id(),
            operation_type=OperationType.empty,
            target_cluster_id=new_cluster.cluster_id,
            target_version_id=new_version.version_id,
        )

        # split edge from source to this new cluster's version.
        await Operation.create_single(
            session,
            operation_id=op_id,
            operation_type=OperationType.cluster_split,
            source_cluster_id=source_cluster.cluster_id,
            source_version_id=src_version_id,
            target_cluster_id=new_cluster.cluster_id,
            target_version_id=new_version.version_id,
        )

        for ref in evidence_refs:
            await Delta.create(
                session,
                cluster_id=new_cluster.cluster_id,
                version_id=new_version.version_id,
                evidence_id=ref.evidence_id,
                evidence_version_id=ref.evidence_version_id,
                delta_type=DeltaType.add,
                actor_id=actor_id,
                weight=ref.weight,
            )

        new_cluster.head_version_id = new_version.version_id
        await materialize_membership(session, new_cluster, new_version.version_id)
        results.append((new_cluster, new_version))

    logger.info(
        "Split cluster %s source_version=%s into %d new clusters",
        source_cluster.cluster_id, src_version_id, len(results),
    )
    return results


# ---------------------------------------------------------------------------
# Membership resolution — spec §4.8.1
# ---------------------------------------------------------------------------


async def resolve_membership(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[ResolvedMember]:
    """Resolve the full membership for a cluster at a specific version.

    Implements the DAG walk algorithm from spec §4.8.1:
    1. Walk all ancestor (cluster_id, version_id) pairs via OPERATION.
    2. Collect all DELTA rows for those pairs.
    3. Sort by delta_id ascending (UUID v6 = creation-time order).
    4. Apply each delta to build the final member set.
    """
    visited: set[tuple[uuid.UUID, uuid.UUID]] = set()
    to_visit: list[tuple[uuid.UUID, uuid.UUID]] = [(cluster_id, version_id)]

    while to_visit:
        curr_cid, curr_vid = to_visit.pop()
        if (curr_cid, curr_vid) in visited:
            continue
        visited.add((curr_cid, curr_vid))

        ancestor_ops = await Operation.get_ancestors_of(session, curr_cid, curr_vid)
        for op in ancestor_ops:
            if op.source_version_id is not None and op.source_cluster_id is not None:
                key = (op.source_cluster_id, op.source_version_id)
                if key not in visited:
                    to_visit.append(key)

    all_deltas: list[Delta] = []
    for cid, vid in visited:
        deltas = await Delta.get_for_version(session, cid, vid)
        all_deltas.extend(deltas)

    all_deltas.sort(key=lambda d: d.delta_id)

    members: dict[uuid.UUID, ResolvedMember] = {}
    for delta in all_deltas:
        if delta.delta_type == DeltaType.add:
            members[delta.evidence_id] = ResolvedMember(
                evidence_id=delta.evidence_id,
                evidence_version_id=delta.evidence_version_id,
                weight=delta.weight,
            )
        else:
            members.pop(delta.evidence_id, None)

    logger.debug(
        "Resolved membership cluster=%s version=%s ancestors=%d members=%d",
        cluster_id, version_id, len(visited), len(members),
    )
    return list(members.values())


# ---------------------------------------------------------------------------
# Uncommitted diff — spec §4.8.2
# ---------------------------------------------------------------------------


async def resolve_pending_diff(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[Delta]:
    """Return the net pending deltas on a working (unsealed) version.

    Spec §4.8.2:
    1. Fetch all deltas for the given version.
    2. Sort by delta_id ascending (creation-time order).
    3. Deduplicate — keep only the latest delta per evidence_id.
    """
    deltas = await Delta.get_for_version(session, cluster_id, version_id)
    latest: dict[uuid.UUID, Delta] = {}
    for delta in deltas:
        latest[delta.evidence_id] = delta

    logger.debug(
        "Resolved pending diff cluster=%s version=%s raw=%d net=%d",
        cluster_id, version_id, len(deltas), len(latest),
    )
    return list(latest.values())


# ---------------------------------------------------------------------------
# Membership materialization
# ---------------------------------------------------------------------------


async def materialize_membership(
    session: AsyncSession,
    cluster: Cluster,
    as_of_version_id: uuid.UUID,
) -> None:
    """Fully re-materialize MEMBERSHIP for a cluster from the DAG.

    Clears existing rows then inserts fresh ones derived from
    ``resolve_membership``.  Must be called in the same transaction as the
    triggering change.
    """
    resolved = await resolve_membership(session, cluster.cluster_id, as_of_version_id)
    await Membership.delete_for_cluster(session, cluster.cluster_id)

    for member in resolved:
        await Membership.upsert(
            session,
            cluster_id=cluster.cluster_id,
            evidence_id=member.evidence_id,
            evidence_version_id=member.evidence_version_id,
            weight=member.weight,
            as_of_version_id=as_of_version_id,
        )

    logger.info(
        "Materialized membership cluster=%s as_of=%s members=%d",
        cluster.cluster_id, as_of_version_id, len(resolved),
    )


async def apply_delta_to_membership(
    session: AsyncSession,
    delta: Delta,
) -> None:
    """Incrementally update MEMBERSHIP for a single DELTA.

    Called immediately after writing a DELTA to keep MEMBERSHIP current
    without a full re-materialization.  Must be called in the same transaction.
    """
    if delta.delta_type == DeltaType.add:
        await Membership.upsert(
            session,
            cluster_id=delta.cluster_id,
            evidence_id=delta.evidence_id,
            evidence_version_id=delta.evidence_version_id,
            weight=delta.weight,
            as_of_version_id=delta.version_id,
        )
    else:
        await Membership.remove_entry(session, delta.cluster_id, delta.evidence_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ConflictError(Exception):
    """Raised by merge_clusters when a conflict_free_join detects conflicts."""

    def __init__(self, evidence_ids: list[uuid.UUID]) -> None:
        super().__init__(f"Conflicting evidence items: {evidence_ids}")
        self.evidence_ids = evidence_ids


def _new_id() -> uuid.UUID:
    from people_gator_api.db.models.base import new_uuid6
    return new_uuid6()
