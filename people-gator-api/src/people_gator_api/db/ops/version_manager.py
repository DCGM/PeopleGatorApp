"""Version manager — high-level multi-step DB operations for the cluster/commit
version graph defined in the product spec.

All public functions accept an ``AsyncSession`` and must be called inside an
active transaction (the caller is responsible for commit / rollback).

Algorithms implemented:
  - initialize_cluster        spec §5.2 initial commit
  - advance_cluster           spec §5.4 ``next`` lineage
  - branch_cluster            spec §5.4 ``branch`` lineage
  - merge_commits             spec §5.4 ``merge`` / ``cluster-merge`` lineage
  - split_cluster             spec §5.4 ``split`` lineage
  - resolve_membership        spec §5.5.1 DAG walk membership resolution
  - resolve_uncommitted_diff  spec §5.5.2 uncommitted diff for a working commit
  - resolve_head_commit       spec §5.5.3 head resolution by head_constraints
  - materialize_membership    spec §5.6 persist resolved state to MEMBERSHIP
  - apply_action_to_membership  incremental MEMBERSHIP update on single ACTION
"""

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.action import Action
from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.commit import Commit
from people_gator_api.db.models.enums import (
    ActionReason,
    ActionType,
    ClusterRole,
    HeadConstraint,
    LineageType,
)
from people_gator_api.db.models.lineage import Lineage
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
) -> tuple[Cluster, Commit]:
    """Create a brand-new cluster with its initial commit and lineage.

    Atomically:
    1. Creates CLUSTER (no head yet).
    2. Creates the initial COMMIT authored by ``actor_id``.
    3. Creates LINEAGE(initial).
    4. Creates ACTION(add) rows for each record in ``initial_records``.
    5. Updates CLUSTER.head_commit_id.
    6. Materializes MEMBERSHIP.

    Returns ``(cluster, commit)``.
    """
    cluster = await Cluster.create(session, cluster_role, head_constraints)
    commit = await Commit.create(session, cluster.cluster_id, cluster_role, actor_id)
    await Lineage.create_initial(session, cluster.cluster_id, commit.commit_id)

    if initial_records:
        for ref in initial_records:
            action = await Action.create(
                session,
                cluster_id=cluster.cluster_id,
                commit_id=commit.commit_id,
                record_id=ref.record_id,
                record_version_id=ref.record_version_id,
                action_type=ActionType.add,
                reason=ref.reason,
                weight=ref.weight,
                actor_id=actor_id,
            )
            await apply_action_to_membership(session, action)

    await cluster.update_head_commit(session, commit.commit_id)

    logger.info(
        "Initialized cluster",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "commit_id": str(commit.commit_id),
            "cluster_role": cluster_role.value,
            "actor_id": str(actor_id),
            "initial_record_count": len(initial_records) if initial_records else 0,
        },
    )
    return cluster, commit


async def advance_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    added_records: list[RecordRef] | None = None,
    removed_records: list[RecordRef] | None = None,
    new_role: ClusterRole | None = None,
) -> Commit:
    """Create the next version of a cluster via a ``next`` lineage entry.

    Atomically:
    1. Creates a new COMMIT authored by ``actor_id``.
    2. Creates LINEAGE(next) from current head to new commit.
    3. Creates ACTION rows for all adds and removes.
    4. Updates CLUSTER.head_commit_id (and role if provided).
    5. Re-materializes MEMBERSHIP from the full DAG.

    Returns the new COMMIT.
    """
    if cluster.head_commit_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head commit — use initialize_cluster first."
        )

    role = new_role or cluster.cluster_role
    old_head = cluster.head_commit_id

    new_commit = await Commit.create(session, cluster.cluster_id, role, actor_id)
    await Lineage.create_next(
        session, cluster.cluster_id, old_head, new_commit.commit_id
    )

    for ref in added_records or []:
        await Action.create(
            session,
            cluster_id=cluster.cluster_id,
            commit_id=new_commit.commit_id,
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
            commit_id=new_commit.commit_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.remove,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    await cluster.update_head_commit(session, new_commit.commit_id, role if new_role else None)
    await materialize_membership(session, cluster, new_commit.commit_id)

    logger.info(
        "Advanced cluster to next version",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "old_commit_id": str(old_head),
            "new_commit_id": str(new_commit.commit_id),
            "actor_id": str(actor_id),
            "added": len(added_records) if added_records else 0,
            "removed": len(removed_records) if removed_records else 0,
            "new_role": new_role.value if new_role else None,
        },
    )
    return new_commit


async def branch_cluster(
    session: AsyncSession,
    cluster: Cluster,
    actor_id: uuid.UUID,
    from_commit_id: uuid.UUID | None = None,
) -> Commit:
    """Create a branch commit off a given (or head) commit.

    ``CLUSTER.head_commit_id`` is NOT updated per spec §5.2.

    Returns the new branch COMMIT.
    """
    source_commit_id = from_commit_id or cluster.head_commit_id
    if source_commit_id is None:
        raise ValueError(
            f"Cluster {cluster.cluster_id} has no head commit and no from_commit_id was provided."
        )

    branch_commit = await Commit.create(
        session, cluster.cluster_id, cluster.cluster_role, actor_id
    )
    await Lineage.create_branch(
        session, cluster.cluster_id, source_commit_id, branch_commit.commit_id
    )

    logger.info(
        "Created branch commit",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "source_commit_id": str(source_commit_id),
            "branch_commit_id": str(branch_commit.commit_id),
            "actor_id": str(actor_id),
        },
    )
    return branch_commit


async def merge_commits(
    session: AsyncSession,
    source_commits: list[tuple[uuid.UUID, uuid.UUID]],
    target_cluster: Cluster,
    actor_id: uuid.UUID,
    new_role: ClusterRole | None = None,
    added_records: list[RecordRef] | None = None,
    removed_records: list[RecordRef] | None = None,
) -> Commit:
    """Merge one or more source commits into a single new target commit.

    ``source_commits`` is a list of ``(cluster_id, commit_id)`` pairs.

    Lineage type:
    - ``merge``         when all sources belong to the same cluster as the target.
    - ``cluster-merge`` when any source is from a different cluster.

    Atomically:
    1. Creates the target COMMIT authored by ``actor_id``.
    2. Creates one LINEAGE row per source commit.
    3. Creates ACTION rows.
    4. Updates CLUSTER.head_commit_id if the current head is among the sources.
    5. Re-materializes MEMBERSHIP.

    Returns the new target COMMIT.
    """
    role = new_role or target_cluster.cluster_role
    merge_commit = await Commit.create(session, target_cluster.cluster_id, role, actor_id)

    for src_cluster_id, src_commit_id in source_commits:
        is_cross = src_cluster_id != target_cluster.cluster_id
        ltype = LineageType.cluster_merge if is_cross else LineageType.merge
        await Lineage.create_merge_entry(
            session,
            source_cluster_id=src_cluster_id,
            source_commit_id=src_commit_id,
            target_cluster_id=target_cluster.cluster_id,
            target_commit_id=merge_commit.commit_id,
            lineage_type=ltype,
        )

    for ref in added_records or []:
        await Action.create(
            session,
            cluster_id=target_cluster.cluster_id,
            commit_id=merge_commit.commit_id,
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
            commit_id=merge_commit.commit_id,
            record_id=ref.record_id,
            record_version_id=ref.record_version_id,
            action_type=ActionType.remove,
            reason=ref.reason,
            weight=ref.weight,
            actor_id=actor_id,
        )

    # Update head if current head is one of the merged sources.
    source_commit_ids = {cid for _, cid in source_commits}
    if target_cluster.head_commit_id in source_commit_ids:
        await target_cluster.update_head_commit(
            session, merge_commit.commit_id, role if new_role else None
        )

    await materialize_membership(session, target_cluster, merge_commit.commit_id)

    logger.info(
        "Merged commits",
        extra={
            "target_cluster_id": str(target_cluster.cluster_id),
            "target_commit_id": str(merge_commit.commit_id),
            "actor_id": str(actor_id),
            "source_count": len(source_commits),
            "new_role": new_role.value if new_role else None,
        },
    )
    return merge_commit


async def split_cluster(
    session: AsyncSession,
    source_cluster: Cluster,
    actor_id: uuid.UUID,
    source_commit_id: uuid.UUID | None = None,
    new_cluster_memberships: list[tuple[ClusterRole, HeadConstraint, list[RecordRef]]] | None = None,
) -> list[tuple[Cluster, Commit]]:
    """Split a cluster into two or more new clusters.

    ``new_cluster_memberships`` is a list of ``(role, constraints, records)``
    tuples, one per split target.

    Atomically:
    1. For each target: creates a new CLUSTER + COMMIT authored by ``actor_id``.
    2. Creates LINEAGE(split) from the source commit to each target commit.
    3. Creates ACTION(add) rows for each target's initial records.
    4. Materializes MEMBERSHIP for each new cluster.

    Returns a list of ``(cluster, commit)`` for each split target.
    """
    src_commit_id = source_commit_id or source_cluster.head_commit_id
    if src_commit_id is None:
        raise ValueError(
            f"Cluster {source_cluster.cluster_id} has no head commit and no source_commit_id was provided."
        )

    results: list[tuple[Cluster, Commit]] = []
    for role, constraints, records in (new_cluster_memberships or []):
        new_cluster = await Cluster.create(session, role, constraints)
        new_commit = await Commit.create(session, new_cluster.cluster_id, role, actor_id)

        await Lineage.create_split_entry(
            session,
            source_cluster_id=source_cluster.cluster_id,
            source_commit_id=src_commit_id,
            target_cluster_id=new_cluster.cluster_id,
            target_commit_id=new_commit.commit_id,
        )

        # Initial lineage entry for the new cluster.
        await Lineage.create_initial(
            session, new_cluster.cluster_id, new_commit.commit_id
        )

        for ref in records:
            await Action.create(
                session,
                cluster_id=new_cluster.cluster_id,
                commit_id=new_commit.commit_id,
                record_id=ref.record_id,
                record_version_id=ref.record_version_id,
                action_type=ActionType.add,
                reason=ref.reason,
                weight=ref.weight,
                actor_id=actor_id,
            )

        await new_cluster.update_head_commit(session, new_commit.commit_id)
        await materialize_membership(session, new_cluster, new_commit.commit_id)
        results.append((new_cluster, new_commit))

    logger.info(
        "Split cluster",
        extra={
            "source_cluster_id": str(source_cluster.cluster_id),
            "source_commit_id": str(src_commit_id),
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
    commit_id: uuid.UUID,
) -> list[ResolvedMember]:
    """Resolve the full membership for a cluster at a specific commit.

    Implements the DAG walk algorithm from spec §5.5.1:
    1. Walk all ancestor (cluster_id, commit_id) pairs via LINEAGE.
    2. Collect all ACTION rows for those pairs.
    3. Sort by action_id ascending (UUID v6 = creation-time order).
    4. Apply each action to build the final member set.
    """
    # BFS/DFS ancestor walk
    visited: set[tuple[uuid.UUID, uuid.UUID]] = set()
    to_visit: list[tuple[uuid.UUID, uuid.UUID]] = [(cluster_id, commit_id)]

    while to_visit:
        curr_cid, curr_coid = to_visit.pop()
        if (curr_cid, curr_coid) in visited:
            continue
        visited.add((curr_cid, curr_coid))

        ancestor_entries = await Lineage.get_ancestors_of(session, curr_cid, curr_coid)
        for entry in ancestor_entries:
            if entry.source_commit_id is not None and entry.source_cluster_id is not None:
                key = (entry.source_cluster_id, entry.source_commit_id)
                if key not in visited:
                    to_visit.append(key)

    # Collect and sort all actions across the DAG
    all_actions: list[Action] = []
    for cid, coid in visited:
        actions = await Action.get_for_commit(session, cid, coid)
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
            "commit_id": str(commit_id),
            "ancestor_commits": len(visited),
            "member_count": len(members),
        },
    )
    return list(members.values())


# ---------------------------------------------------------------------------
# Uncommitted diff — spec §5.5.2
# ---------------------------------------------------------------------------


async def resolve_uncommitted_diff(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    commit_id: uuid.UUID,
) -> list[Action]:
    """Return the net uncommitted actions on a working commit.

    Spec §5.5.2:
    1. Fetch all actions for the given commit.
    2. Sort by action_id ascending.
    3. Deduplicate — keep only the latest action per record_id.
    """
    actions = await Action.get_for_commit(session, cluster_id, commit_id)
    # actions are already sorted ascending from get_for_commit
    latest: dict[uuid.UUID, Action] = {}
    for action in actions:
        latest[action.record_id] = action

    logger.debug(
        "Resolved uncommitted diff",
        extra={
            "cluster_id": str(cluster_id),
            "commit_id": str(commit_id),
            "action_count": len(actions),
            "net_diff_count": len(latest),
        },
    )
    return list(latest.values())


# ---------------------------------------------------------------------------
# Head commit resolution — spec §5.5.3
# ---------------------------------------------------------------------------


async def resolve_head_commit(
    session: AsyncSession,
    cluster: Cluster,
) -> uuid.UUID:
    """Return the effective head commit_id for a cluster.

    Behaviour depends on ``cluster.head_constraints``:
    - ``locked``: always the initial commit.
    - ``main``:   follow the ``next``/``merge`` chain from initial.
    - ``any``:    the spec says to return all leaf commits; here we return the
                  latest leaf (highest commit_id) for a single-value interface.
                  Callers that need all leaves should use
                  ``resolve_all_head_commits``.
    """
    if cluster.head_constraints == HeadConstraint.locked:
        initial_id = await Lineage.get_initial_commit_id(
            session, cluster.cluster_id
        )
        if initial_id is None:
            raise LookupError(
                f"Cluster {cluster.cluster_id} has no initial lineage entry."
            )
        return initial_id

    if cluster.head_constraints == HeadConstraint.main:
        return await _resolve_main_head(session, cluster.cluster_id)

    # HeadConstraint.any — return the most recent leaf
    leaves = await resolve_all_head_commits(session, cluster)
    if not leaves:
        raise LookupError(
            f"Cluster {cluster.cluster_id} has no leaf commits."
        )
    return max(leaves)


async def resolve_all_head_commits(
    session: AsyncSession,
    cluster: Cluster,
) -> list[uuid.UUID]:
    """Return all leaf commit IDs for a cluster (used with ``any`` constraint).

    A leaf commit has no outgoing ``next`` or ``merge`` lineage entry.
    """
    all_entries = await Lineage.get_for_cluster(session, cluster.cluster_id)

    # Build set of commit IDs that have an outgoing next/merge edge.
    has_successor: set[uuid.UUID] = set()
    for entry in all_entries:
        if (
            entry.source_cluster_id == cluster.cluster_id
            and entry.lineage_type in (LineageType.next, LineageType.merge)
            and entry.source_commit_id is not None
        ):
            has_successor.add(entry.source_commit_id)

    leaves = [
        entry.target_commit_id
        for entry in all_entries
        if entry.target_commit_id not in has_successor
    ]
    return list(set(leaves))  # deduplicate


async def _resolve_main_head(
    session: AsyncSession,
    cluster_id: uuid.UUID,
) -> uuid.UUID:
    """Walk the ``next``/``merge`` chain to find the main-line head.

    Implements spec §5.5.3 case ``main``.
    """
    all_entries = await Lineage.get_for_cluster(session, cluster_id)
    # Sort ascending by target_commit_id (UUID v6 = time order).
    all_entries.sort(key=lambda e: e.target_commit_id)

    initial = next(
        (e for e in all_entries if e.lineage_type == LineageType.initial),
        None,
    )
    if initial is None:
        raise LookupError(f"Cluster {cluster_id} has no initial lineage entry.")

    head = initial.target_commit_id

    for entry in all_entries:
        if (
            entry.lineage_type == LineageType.next
            and entry.source_commit_id == head
        ):
            head = entry.target_commit_id
        elif (
            entry.lineage_type == LineageType.merge
            and entry.source_commit_id == head
        ):
            head = entry.target_commit_id
        elif (
            entry.lineage_type == LineageType.cluster_merge
            and entry.source_cluster_id == cluster_id
            and entry.source_commit_id == head
        ):
            head = entry.target_commit_id

    return head


# ---------------------------------------------------------------------------
# Membership materialization — spec §5.6
# ---------------------------------------------------------------------------


async def materialize_membership(
    session: AsyncSession,
    cluster: Cluster,
    as_of_commit_id: uuid.UUID,
) -> None:
    """Fully re-materialize MEMBERSHIP for a cluster from the DAG.

    Clears existing rows then inserts fresh ones derived from
    ``resolve_membership``.  Must be called in the same transaction as the
    triggering change.
    """
    resolved = await resolve_membership(
        session, cluster.cluster_id, as_of_commit_id
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
            as_of_commit_id=as_of_commit_id,
        )

    logger.info(
        "Materialized membership",
        extra={
            "cluster_id": str(cluster.cluster_id),
            "as_of_commit_id": str(as_of_commit_id),
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
            as_of_commit_id=action.commit_id,
        )
    else:
        await Membership.delete_record(
            session, action.cluster_id, action.record_id
        )
