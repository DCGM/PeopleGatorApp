"""Version manager — high-level multi-step DB operations for the cluster/version
graph defined in the product spec.

All public functions accept an ``AsyncSession`` and must be called inside an
active transaction (the caller is responsible for commit / rollback).

Algorithms implemented:
  - initialize_cluster        spec §5.2 initial version
  - advance_cluster           spec §5.4 ``next`` transition
  - branch_cluster            spec §5.4 ``branch`` transition
  - merge_versions            spec §5.4 ``merge`` / ``cluster-merge`` transition
  - split_cluster             spec §5.4 ``split`` transition
  - resolve_membership        spec §5.5.1 DAG walk membership resolution
  - resolve_pending_diff      spec §5.5.2 pending diff for a working version
  - resolve_head_version      spec §5.5.3 head resolution by head_constraints
  - materialize_membership    spec §5.6 persist resolved state to MEMBERSHIP
  - apply_action_to_membership  incremental MEMBERSHIP update on single ACTION
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.action import Action
from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.version import Version
from people_gator_api.db.models.enums import (
    ActionReason,
    ActionType,
    ClusterRole,
    HeadConstraint,
    TransitionType,
)
from people_gator_api.db.models.transition import Transition
from people_gator_api.db.models.membership import Membership

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal data-transfer type
# ---------------------------------------------------------------------------


@dataclass
class RecordRef:
    """Minimal reference to a specific record version with association weight."""

    record_id: uuid.UUID
    record_version_id: uuid.UUID
    weight: float = 1.0
    reason: ActionReason = ActionReason.automatic_linking


@dataclass
class ResolvedMember:
    """One entry in a resolved cluster membership snapshot."""

    record_id: uuid.UUID
    record_version_id: uuid.UUID
    weight: float
    reason: str


# ---------------------------------------------------------------------------
# High-level versioning operations
# ---------------------------------------------------------------------------


async def initialize_cluster(
    session: AsyncSession,
    cluster_role: ClusterRole,
    head_constraints: HeadConstraint,
    actor_id: uuid.UUID,
    initial_records: list[RecordRef] | None = None,
) -> tuple[Cluster, Version]:
    """Create a brand-new cluster with its initial version and transition.

    Atomically:
    1. Creates CLUSTER (no head yet).
    2. Creates the initial VERSION authored by ``actor_id``.
    3. Creates TRANSITION(initial).
    4. Creates ACTION(add) rows for each record in ``initial_records``.
    5. Updates CLUSTER.head_version_id.
    6. Materializes MEMBERSHIP.

    Returns ``(cluster, version)``.
    """
    cluster = await Cluster.create(session, cluster_role, head_constraints)
    version = await Version.create(session, cluster.cluster_id, cluster_role, actor_id)
    await Transition.create_initial(session, cluster.cluster_id, version.version_id)

    if initial_records:
        for ref in initial_records:
            action = await Action.create(
                session,
                cluster_id=cluster.cluster_id,
                version_id=version.version_id,
                record_id=ref.record_id,
                record_version_id=ref.record_version_id,
                action_type=ActionType.add,
                reason=ref.reason,
                weight=ref.weight,
                actor_id=actor_id,
            )
            await apply_action_to_membership(session, action)

    await cluster.update_head_version(session, version.version_id)

    logger.info(
        "Initialized cluster",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "version_id": str(version.version_id),
            "cluster_role": cluster_role.value,
            "actor_id": str(actor_id),
            "initial_record_count": len(initial_records) if initial_records else 0,
        },
    )
    return cluster, version


async def advance_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    added_records: list[RecordRef] | None = None,
    removed_records: list[RecordRef] | None = None,
    new_role: ClusterRole | None = None,
) -> Version:
    """Create the next version of a cluster via a ``next`` transition entry.

    Atomically:
    1. Creates a new VERSION authored by ``actor_id``.
    2. Creates TRANSITION(next) from current head to new version.
    3. Creates ACTION rows for all adds and removes.
    4. Updates CLUSTER.head_version_id (and role if provided).
    5. Re-materializes MEMBERSHIP from the full DAG.

    Returns the new VERSION.
    """
    if cluster.head_version_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head version — use initialize_cluster first."
        )

    role = new_role or cluster.cluster_role
    old_head = cluster.head_version_id

    new_version = await Version.create(session, cluster.cluster_id, role, actor_id)
    await Transition.create_next(
        session, cluster.cluster_id, old_head, new_version.version_id
    )

    for ref in added_records or []:
        await Action.create(
            session,
            cluster_id=cluster.cluster_id,
            version_id=new_version.version_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.add,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    for ref in removed_records or []:
        await Action.create(
            session,
            cluster_id=cluster.cluster_id,
            version_id=new_version.version_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.remove,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    await cluster.update_head_version(session, new_version.version_id, role if new_role else None)
    await materialize_membership(session, cluster, new_version.version_id)

    logger.info(
        "Advanced cluster to next version",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "old_version_id": str(old_head),
            "new_version_id": str(new_version.version_id),
            "actor_id": str(actor_id),
            "added": len(added_records) if added_records else 0,
            "removed": len(removed_records) if removed_records else 0,
            "new_role": new_role.value if new_role else None,
        },
    )
    return new_version


async def branch_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    from_version_id: uuid.UUID | None = None,
) -> Version:
    """Create a branch version off a given (or head) version.

    ``CLUSTER.head_version_id`` is NOT updated per spec §5.2.

    Returns the new branch VERSION.
    """
    source_version_id = from_version_id or cluster.head_version_id
    if source_version_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head version and no from_version_id was provided."
        )

    branch_version = await Version.create(
        session, cluster.cluster_id, cluster.cluster_role, actor_id
    )
    await Transition.create_branch(
        session, cluster.cluster_id, source_version_id, branch_version.version_id
    )

    logger.info(
        "Created branch version",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "source_version_id": str(source_version_id),
            "branch_version_id": str(branch_version.version_id),
            "actor_id": str(actor_id),
        },
    )
    return branch_version


async def merge_versions(
    session: AsyncSession,
    source_versions: list[tuple[uuid.UUID, uuid.UUID]],
    target_cluster: Cluster,
    actor_id: uuid.UUID,
    new_role: ClusterRole | None = None,
    added_records: list[RecordRef] | None = None,
    removed_records: list[RecordRef] | None = None,
) -> Version:
    """Merge one or more source versions into a single new target version.

    ``source_versions`` is a list of ``(cluster_id, version_id)`` pairs.

    Transition type:
    - ``merge``         when all sources belong to the same cluster as the target.
    - ``cluster-merge`` when any source is from a different cluster.

    Atomically:
    1. Creates the target VERSION authored by ``actor_id``.
    2. Creates one TRANSITION row per source version.
    3. Creates ACTION rows.
    4. Updates CLUSTER.head_version_id if the current head is among the sources.
    5. Re-materializes MEMBERSHIP.

    Returns the new target VERSION.
    """
    role = new_role or target_cluster.cluster_role
    merge_version = await Version.create(session, target_cluster.cluster_id, role, actor_id)

    for src_cluster_id, src_version_id in source_versions:
        is_cross = src_cluster_id != target_cluster.cluster_id
        ltype = TransitionType.cluster_merge if is_cross else TransitionType.merge
        await Transition.create_merge_entry(
            session,
            source_cluster_id=src_cluster_id,
            source_version_id=src_version_id,
            target_cluster_id=target_cluster.cluster_id,
            target_version_id=merge_version.version_id,
            transition_type=ltype,
        )

    for ref in added_records or []:
        await Action.create(
            session,
            cluster_id=target_cluster.cluster_id,
            version_id=merge_version.version_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.add,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    for ref in removed_records or []:
        await Action.create(
            session,
            cluster_id=target_cluster.cluster_id,
            version_id=merge_version.version_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.remove,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    # Update head if current head is one of the merged sources.
    source_version_ids = {vid for _, vid in source_versions}
    if target_cluster.head_version_id in source_version_ids:
        await target_cluster.update_head_version(
            session, merge_version.version_id, role if new_role else None
        )

    await materialize_membership(session, target_cluster, merge_version.version_id)

    logger.info(
        "Merged versions",
        extra={
            "target_cluster_id": str(target_cluster.cluster_id),
            "target_version_id": str(merge_version.version_id),
            "actor_id": str(actor_id),
            "source_count": len(source_versions),
            "new_role": new_role.value if new_role else None,
        },
    )
    return merge_version


async def split_cluster(
    session: AsyncSession,
    source_cluster: Cluster,
    actor_id: uuid.UUID,
    source_version_id: uuid.UUID | None = None,
    new_cluster_memberships: list[tuple[ClusterRole, HeadConstraint, list[RecordRef]]] | None = None,
) -> list[tuple[Cluster, Version]]:
    """Split a cluster into two or more new clusters.

    ``new_cluster_memberships`` is a list of ``(role, constraints, records)``
    tuples, one per split target.

    Atomically:
    1. For each target: creates a new CLUSTER + VERSION authored by ``actor_id``.
    2. Creates TRANSITION(split) from the source version to each target version.
    3. Creates ACTION(add) rows for each target's initial records.
    4. Materializes MEMBERSHIP for each new cluster.

    Returns a list of ``(cluster, version)`` for each split target.
    """
    src_version_id = source_version_id or source_cluster.head_version_id
    if src_version_id is None:
        raise ValueError(
            f"Cluster {source_cluster.cluster_id} has no head version and no source_version_id was provided."
        )

    results: list[tuple[Cluster, Version]] = []
    for role, constraints, records in (new_cluster_memberships or []):
        new_cluster = await Cluster.create(session, role, constraints)
        new_version = await Version.create(session, new_cluster.cluster_id, role, actor_id)

        await Transition.create_split_entry(
            session,
            source_cluster_id=source_cluster.cluster_id,
            source_version_id=src_version_id,
            target_cluster_id=new_cluster.cluster_id,
            target_version_id=new_version.version_id,
        )

        # Initial transition entry for the new cluster.
        await Transition.create_initial(
            session, new_cluster.cluster_id, new_version.version_id
        )

        for ref in records:
            await Action.create(
                session,
                cluster_id=new_cluster.cluster_id,
                version_id=new_version.version_id,
                record_id=ref.record_id,
                record_version_id=ref.record_version_id,
                action_type=ActionType.add,
                reason=ref.reason,
                weight=ref.weight,
                actor_id=actor_id,
            )

        await new_cluster.update_head_version(session, new_version.version_id)
        await materialize_membership(session, new_cluster, new_version.version_id)
        results.append((new_cluster, new_version))

    logger.info(
        "Split cluster",
        extra={
            "source_cluster_id": str(source_cluster.cluster_id),
            "source_version_id": str(src_version_id),
            "actor_id": str(actor_id),
            "split_count": len(results),
        },
    )
    return results


# ---------------------------------------------------------------------------
# Membership resolution — spec §5.5.1
# ---------------------------------------------------------------------------


async def resolve_membership(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[ResolvedMember]:
    """Resolve the full membership for a cluster at a specific version.

    Implements the DAG walk algorithm from spec §5.5.1:
    1. Walk all ancestor (cluster_id, version_id) pairs via TRANSITION.
    2. Collect all ACTION rows for those pairs.
    3. Sort by action_id ascending (UUID v6 = creation-time order).
    4. Apply each action to build the final member set.
    """
    # BFS/DFS ancestor walk
    visited: set[tuple[uuid.UUID, uuid.UUID]] = set()
    to_visit: list[tuple[uuid.UUID, uuid.UUID]] = [(cluster_id, version_id)]

    while to_visit:
        curr_cid, curr_vid = to_visit.pop()
        if (curr_cid, curr_vid) in visited:
            continue
        visited.add((curr_cid, curr_vid))

        ancestor_entries = await Transition.get_ancestors_of(session, curr_cid, curr_vid)
        for entry in ancestor_entries:
            if entry.source_version_id is not None and entry.source_cluster_id is not None:
                key = (entry.source_cluster_id, entry.source_version_id)
                if key not in visited:
                    to_visit.append(key)

    # Collect and sort all actions across the DAG
    all_actions: list[Action] = []
    for cid, vid in visited:
        actions = await Action.get_for_version(session, cid, vid)
        all_actions.extend(actions)

    all_actions.sort(key=lambda a: a.action_id)

    # Apply sequentially
    members: dict[uuid.UUID, ResolvedMember] = {}
    for action in all_actions:
        if action.action_type == ActionType.add:
            members[action.record_id] = ResolvedMember(
                record_id=action.record_id,
                record_version_id=action.record_version_id,
                weight=action.weight,
                reason=action.reason,
            )
        else:
            members.pop(action.record_id, None)

    logger.debug(
        "Resolved cluster membership",
        extra={
            "cluster_id": str(cluster_id),
            "version_id": str(version_id),
            "ancestor_versions": len(visited),
            "member_count": len(members),
        },
    )
    return list(members.values())


# ---------------------------------------------------------------------------
# Uncommitted diff — spec §5.5.2
# ---------------------------------------------------------------------------


async def resolve_pending_diff(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
) -> list[Action]:
    """Return the net pending actions on a working version.

    Spec §5.5.2:
    1. Fetch all actions for the given version.
    2. Sort by action_id ascending.
    3. Deduplicate — keep only the latest action per record_id.
    """
    actions = await Action.get_for_version(session, cluster_id, version_id)
    # actions are already sorted ascending from get_for_version
    latest: dict[uuid.UUID, Action] = {}
    for action in actions:
        latest[action.record_id] = action

    logger.debug(
        "Resolved pending diff",
        extra={
            "cluster_id": str(cluster_id),
            "version_id": str(version_id),
            "action_count": len(actions),
            "net_diff_count": len(latest),
        },
    )
    return list(latest.values())


# ---------------------------------------------------------------------------
# Head commit resolution — spec §5.5.3
# ---------------------------------------------------------------------------


async def resolve_head_version(
    session: AsyncSession,
    cluster: Cluster,
) -> uuid.UUID:
    """Return the effective head version_id for a cluster.

    Behaviour depends on ``cluster.head_constraints``:
    - ``locked``: always the initial version.
    - ``main``:   follow the ``next``/``merge`` chain from initial.
    - ``any``:    the spec says to return all leaf versions; here we return the
                  latest leaf (highest version_id) for a single-value interface.
                  Callers that need all leaves should use
                  ``resolve_all_head_versions``.
    """
    if cluster.head_constraints == HeadConstraint.locked:
        initial_id = await Transition.get_initial_version_id(
            session, cluster.cluster_id
        )
        if initial_id is None:
            raise LookupError(
                f"Cluster {cluster.cluster_id} has no initial transition entry."
            )
        return initial_id

    if cluster.head_constraints == HeadConstraint.main:
        return await _resolve_main_head(session, cluster.cluster_id)

    # HeadConstraint.any — return the most recent leaf
    leaves = await resolve_all_head_versions(session, cluster)
    if not leaves:
        raise LookupError(
            f"Cluster {cluster.cluster_id} has no leaf versions."
        )
    return max(leaves)


async def resolve_all_head_versions(
    session: AsyncSession,
    cluster: Cluster,
) -> list[uuid.UUID]:
    """Return all leaf version IDs for a cluster (used with ``any`` constraint).

    A leaf version has no outgoing ``next`` or ``merge`` transition entry.
    """
    all_entries = await Transition.get_for_cluster(session, cluster.cluster_id)

    # Build set of version IDs that have an outgoing next/merge edge.
    has_successor: set[uuid.UUID] = set()
    for entry in all_entries:
        if (
            entry.source_cluster_id == cluster.cluster_id
            and entry.transition_type in (TransitionType.next, TransitionType.merge)
            and entry.source_version_id is not None
        ):
            has_successor.add(entry.source_version_id)

    leaves = [
        entry.target_version_id
        for entry in all_entries
        if entry.target_version_id not in has_successor
    ]
    return list(set(leaves))  # deduplicate


async def _resolve_main_head(
    session: AsyncSession,
    cluster_id: uuid.UUID,
) -> uuid.UUID:
    """Walk the ``next``/``merge`` chain to find the main-line head.

    Implements spec §5.5.3 case ``main``.
    """
    all_entries = await Transition.get_for_cluster(session, cluster_id)
    # Sort ascending by target_version_id (UUID v6 = time order).
    all_entries.sort(key=lambda e: e.target_version_id)

    initial = next(
        (e for e in all_entries if e.transition_type == TransitionType.initial),
        None,
    )
    if initial is None:
        raise LookupError(f"Cluster {cluster_id} has no initial transition entry.")

    head = initial.target_version_id

    for entry in all_entries:
        if (
            entry.transition_type == TransitionType.next
            and entry.source_version_id == head
        ):
            head = entry.target_version_id
        elif (
            entry.transition_type == TransitionType.merge
            and entry.source_version_id == head
        ):
            head = entry.target_version_id
        elif (
            entry.transition_type == TransitionType.cluster_merge
            and entry.source_cluster_id == cluster_id
            and entry.source_version_id == head
        ):
            head = entry.target_version_id

    return head


# ---------------------------------------------------------------------------
# Membership materialization — spec §5.6
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
    resolved = await resolve_membership(
        session, cluster.cluster_id, as_of_version_id
    )
    await Membership.delete_all_for_cluster(session, cluster.cluster_id)

    for member in resolved:
        await Membership.upsert(
            session,
            cluster_id=cluster.cluster_id,
            record_id=member.record_id,
            record_version_id=member.record_version_id,
            weight=member.weight,
            reason=member.reason,
            as_of_version_id=as_of_version_id,
        )

    logger.info(
        "Materialized membership",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "as_of_version_id": str(as_of_version_id),
            "member_count": len(resolved),
        },
    )


async def apply_action_to_membership(
    session: AsyncSession,
    action: Action,
) -> None:
    """Incrementally update MEMBERSHIP for a single ACTION.

    Called immediately after writing an ACTION to keep MEMBERSHIP current
    without a full re-materialization.  Must be called in the same transaction.
    """
    if action.action_type == ActionType.add:
        await Membership.upsert(
            session,
            cluster_id=action.cluster_id,
            record_id=action.record_id,
            record_version_id=action.record_version_id,
            weight=action.weight,
            reason=action.reason,
            as_of_version_id=action.version_id,
        )
    else:
        await Membership.delete_record(
            session, action.cluster_id, action.record_id
        )
