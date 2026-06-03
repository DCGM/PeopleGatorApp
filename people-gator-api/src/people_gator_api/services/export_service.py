import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.membership import Membership
from people_gator_api.db.models.task import Task


async def export_cluster_state(
    session: AsyncSession,
    cluster_ids: list[uuid.UUID],
    include_history: bool,
) -> dict[str, object]:
    items: list[dict[str, object]] = []
    for cluster_id in cluster_ids:
        cluster = await Cluster.get(session, cluster_id)
        if cluster is None:
            continue
        memberships = await Membership.get_for_cluster(session, cluster_id)
        members = [
            {
                "evidence_id": str(member.evidence_id),
                "evidence_version_id": str(member.evidence_version_id),
                "weight": member.weight,
            }
            for member in memberships
        ]
        items.append(
            {
                "cluster_id": str(cluster.cluster_id),
                "head_version_id": str(cluster.head_version_id) if cluster.head_version_id else None,
                "members": members,
                "version_history": [] if include_history else [],
            }
        )
    return {"clusters": items}


async def export_inter_annotator_agreement(
    session: AsyncSession,
    cluster_id: uuid.UUID,
    pinned_version_id: uuid.UUID,
) -> dict[str, object]:
    tasks = await Task.list_for_cluster(session, cluster_id)
    filtered = [
        task
        for task in tasks
        if task.pinned_version_id == pinned_version_id
    ]

    return {
        "cluster_id": str(cluster_id),
        "pinned_version_id": str(pinned_version_id),
        "task_count": len(filtered),
        "pairwise_jaccard": [],
        "fleiss_kappa": None,
    }
