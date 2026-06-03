"""Cluster sync service — synchronises Postgres MEMBERSHIP rows to Weaviate.

ClusterSyncService maintains two Weaviate collections:

EvidenceEmbedding
    One document per (evidence_id, evidence_version_id) pair.  Callers are
    responsible for supplying the pre-computed embedding vector at upsert
    time; this service does not generate embeddings.  The Weaviate UUID
    assigned to each document is deterministic (UUID5 from evidence_id +
    evidence_version_id) and requires no back-reference stored on EVIDENCE.
    ``producer_id`` is stored as a filterable payload property.

ClusterSnapshot
    One document per cluster.  Synced by reading the materialised
    MEMBERSHIP table from Postgres, fetching the per-member vectors from
    EvidenceEmbedding, computing per-modality centroid vectors, and
    upserting a ClusterSnapshot document with named vectors for face and
    name modalities.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

import weaviate.exceptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weaviate import WeaviateAsyncClient

from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.enums import EvidenceType
from people_gator_api.db.models.evidence import Evidence
from people_gator_api.db.models.membership import Membership
from people_gator_api.vector.schema import (
    CLUSTER_SNAPSHOT_COLLECTION,
    FACE_VECTOR,
    NAME_VECTOR,
    RECORD_EMBEDDING_COLLECTION,
)

logger = logging.getLogger(__name__)

_EVIDENCE_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_CLUSTER_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def evidence_weaviate_uuid(evidence_id: uuid.UUID, evidence_version_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for an EvidenceEmbedding document."""
    return uuid.uuid5(_EVIDENCE_NS, f"evidence:{evidence_id}:{evidence_version_id}")


def cluster_weaviate_uuid(cluster_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for a ClusterSnapshot document."""
    return uuid.uuid5(_CLUSTER_NS, f"cluster:{cluster_id}")


class ClusterSyncService:
    """Async service that mirrors Postgres cluster state into Weaviate."""

    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def upsert_evidence_embedding(
        self,
        evidence: Evidence,
        vector: list[float],
        *,
        cluster_id: uuid.UUID | None = None,
        membership_weight: float | None = None,
    ) -> uuid.UUID:
        """Upsert an EvidenceEmbedding document and return its Weaviate UUID."""
        wv_uuid = evidence_weaviate_uuid(evidence.evidence_id, evidence.evidence_version_id)
        props: dict[str, Any] = {
            "evidence_id": str(evidence.evidence_id),
            "evidence_version_id": str(evidence.evidence_version_id),
            "evidence_type": evidence.evidence_type.value,
            "source_id": str(evidence.source_id),
        }
        if cluster_id is not None:
            props["cluster_id"] = str(cluster_id)
        if membership_weight is not None:
            props["membership_weight"] = membership_weight

        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        await _upsert_object(collection, wv_uuid=wv_uuid, properties=props, vector=vector)
        logger.debug("Upserted EvidenceEmbedding %s (evidence_id=%s)", wv_uuid, evidence.evidence_id)
        return wv_uuid

    async def remove_evidence_embedding(
        self, evidence_id: uuid.UUID, evidence_version_id: uuid.UUID
    ) -> None:
        """Delete an EvidenceEmbedding document. No-ops if not found."""
        wv_uuid = evidence_weaviate_uuid(evidence_id, evidence_version_id)
        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)

    async def sync_cluster(
        self,
        cluster_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Sync a cluster's materialised MEMBERSHIP state to Weaviate."""
        cluster = await Cluster.get(session, cluster_id)
        if cluster is None:
            logger.warning("sync_cluster called for unknown cluster_id=%s", cluster_id)
            return

        memberships = await Membership.get_for_cluster(session, cluster_id)

        evidence_ids = {m.evidence_id for m in memberships}
        evidence_map: dict[uuid.UUID, Evidence] = {}
        if evidence_ids:
            result = await session.execute(
                select(Evidence).where(Evidence.evidence_id.in_(evidence_ids))
            )
            for ev in result.scalars().all():
                evidence_map[ev.evidence_id] = ev

        face_items = [
            evidence_map[m.evidence_id]
            for m in memberships
            if evidence_map.get(m.evidence_id) is not None
            and evidence_map[m.evidence_id].evidence_type == EvidenceType.face_detection
        ]
        name_items = [
            evidence_map[m.evidence_id]
            for m in memberships
            if evidence_map.get(m.evidence_id) is not None
            and evidence_map[m.evidence_id].evidence_type == EvidenceType.named_entity
        ]

        face_centroid = await self._compute_centroid_from_weaviate(face_items)
        name_centroid = await self._compute_centroid_from_weaviate(name_items)

        face_count = len(face_items)
        named_entity_count = len(name_items)
        text_region_count = sum(
            1 for m in memberships
            if evidence_map.get(m.evidence_id) is not None
            and evidence_map[m.evidence_id].evidence_type == EvidenceType.text_region
        )

        props: dict[str, Any] = {
            "cluster_id": str(cluster_id),
            "face_count": face_count,
            "named_entity_count": named_entity_count,
            "text_region_count": text_region_count,
        }
        if cluster.head_version_id is not None:
            props["as_of_version_id"] = str(cluster.head_version_id)

        named_vectors: dict[str, list[float]] = {}
        if face_centroid is not None:
            named_vectors[FACE_VECTOR] = face_centroid
        if name_centroid is not None:
            named_vectors[NAME_VECTOR] = name_centroid

        wv_uuid = cluster_weaviate_uuid(cluster_id)
        collection = self._client.collections.get(CLUSTER_SNAPSHOT_COLLECTION)
        await _upsert_object(
            collection,
            wv_uuid=wv_uuid,
            properties=props,
            vector=named_vectors if named_vectors else None,
        )
        logger.info(
            "Synced ClusterSnapshot %s (cluster_id=%s, face=%d, name=%d)",
            wv_uuid, cluster_id, face_count, named_entity_count,
        )

    async def remove_cluster_snapshot(self, cluster_id: uuid.UUID) -> None:
        """Delete a ClusterSnapshot document. No-ops if not found."""
        wv_uuid = cluster_weaviate_uuid(cluster_id)
        collection = self._client.collections.get(CLUSTER_SNAPSHOT_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)

    async def sync_evidence_cluster_membership(
        self,
        evidence_id: uuid.UUID,
        evidence_version_id: uuid.UUID,
        cluster_id: uuid.UUID | None,
    ) -> None:
        """Update the cluster_id property on an existing EvidenceEmbedding."""
        wv_uuid = evidence_weaviate_uuid(evidence_id, evidence_version_id)
        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        props: dict[str, Any] = {
            "cluster_id": str(cluster_id) if cluster_id is not None else None,
        }
        try:
            await collection.data.update(uuid=wv_uuid, properties=props)
        except weaviate.exceptions.UnexpectedStatusCodeError as exc:
            if exc.status_code == 404:
                logger.debug(
                    "EvidenceEmbedding %s not found during membership sync (evidence_id=%s)",
                    wv_uuid, evidence_id,
                )
            else:
                raise

    async def _compute_centroid_from_weaviate(
        self,
        evidence_items: list[Evidence],
    ) -> list[float] | None:
        """Fetch vectors from EvidenceEmbedding and return their centroid."""
        if not evidence_items:
            return None

        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        vectors: list[list[float]] = []
        for ev in evidence_items:
            wv_uuid = evidence_weaviate_uuid(ev.evidence_id, ev.evidence_version_id)
            try:
                obj = await collection.query.fetch_object_by_id(
                    uuid=wv_uuid,
                    include_vector=True,
                )
                if obj.vector:
                    raw = obj.vector.get("default")
                    if isinstance(raw, list) and raw and isinstance(raw[0], float):
                        vectors.append(cast(list[float], raw))
            except Exception:
                logger.debug(
                    "Failed to fetch vector for evidence_id=%s evidence_version_id=%s from Weaviate",
                    ev.evidence_id, ev.evidence_version_id,
                )

        return _centroid(vectors)


def _centroid(vectors: list[list[float]]) -> list[float] | None:
    """Compute the element-wise mean of a list of equal-dimension vectors."""
    if not vectors:
        return None
    dim = len(vectors[0])
    n = len(vectors)
    return [sum(v[i] for v in vectors) / n for i in range(dim)]


async def _upsert_object(
    collection: Any,
    *,
    wv_uuid: uuid.UUID,
    properties: dict[str, Any],
    vector: list[float] | dict[str, list[float]] | None,
) -> None:
    """Insert or replace a Weaviate object (upsert semantics)."""
    try:
        await collection.data.insert(
            uuid=wv_uuid,
            properties=properties,
            vector=vector,
        )
    except weaviate.exceptions.UnexpectedStatusCodeError as exc:
        if exc.status_code == 409:
            await collection.data.replace(
                uuid=wv_uuid,
                properties=properties,
                vector=vector,
            )
        else:
            raise
