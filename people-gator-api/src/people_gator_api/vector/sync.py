"""Cluster sync service — synchronises Postgres MEMBERSHIP rows to Weaviate.

ClusterSyncService maintains two Weaviate collections:

RecordEmbedding
    One document per (record_id, record_version_id) pair.  Callers are
    responsible for supplying the pre-computed embedding vector at upsert
    time; this service does not generate embeddings.  The Weaviate UUID
    assigned to each document is deterministic (UUID5 from record_id) so
    it can be stored back on RECORD.embedding_id.

ClusterSnapshot
    One document per cluster.  Synced by reading the materialised
    MEMBERSHIP table from Postgres, fetching the per-member vectors from
    RecordEmbedding, computing per-modality centroid vectors, and
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
from people_gator_api.db.models.enums import RecordType
from people_gator_api.db.models.membership import Membership
from people_gator_api.db.models.record import Record
from people_gator_api.vector.schema import (
    CLUSTER_SNAPSHOT_COLLECTION,
    FACE_VECTOR,
    NAME_VECTOR,
    RECORD_EMBEDDING_COLLECTION,
)

logger = logging.getLogger(__name__)

# Namespace for deterministic UUID generation.
_RECORD_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID URL namespace
_CLUSTER_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def record_weaviate_uuid(record_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for a RecordEmbedding document."""
    return uuid.uuid5(_RECORD_NS, f"record:{record_id}")


def cluster_weaviate_uuid(cluster_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for a ClusterSnapshot document."""
    return uuid.uuid5(_CLUSTER_NS, f"cluster:{cluster_id}")


class ClusterSyncService:
    """Async service that mirrors Postgres cluster state into Weaviate.

    Instantiate with a connected :class:`~weaviate.WeaviateAsyncClient`.
    """

    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    # ------------------------------------------------------------------
    # Record embedding management
    # ------------------------------------------------------------------

    async def upsert_record_embedding(
        self,
        record: Record,
        vector: list[float],
        *,
        cluster_id: uuid.UUID | None = None,
        membership_weight: float | None = None,
        membership_reason: str | None = None,
    ) -> uuid.UUID:
        """Upsert a RecordEmbedding document and return its Weaviate UUID.

        The returned UUID is deterministic and equals
        ``record_weaviate_uuid(record.record_id)``.  Callers should persist
        this value to ``RECORD.embedding_id`` so searches can be linked back
        to the originating Postgres row.

        Args:
            record: The SQLAlchemy Record ORM instance.
            vector: Pre-computed embedding vector.
            cluster_id: Optional current cluster membership.
            membership_weight: Optional membership weight.
            membership_reason: Optional membership reason string.

        Returns:
            The Weaviate UUID (deterministic, based on record_id).
        """
        wv_uuid = record_weaviate_uuid(record.record_id)
        props: dict[str, Any] = {
            "record_id": str(record.record_id),
            "record_version_id": str(record.record_version_id),
            "record_type": record.record_type.value,
            "source_id": str(record.source_id),
        }
        if cluster_id is not None:
            props["cluster_id"] = str(cluster_id)
        if membership_weight is not None:
            props["membership_weight"] = membership_weight
        if membership_reason is not None:
            props["membership_reason"] = membership_reason

        # Extract confidence and model_version from metadata_ if present.
        if record.metadata_:
            if "confidence" in record.metadata_:
                props["confidence"] = float(record.metadata_["confidence"])
            if "model_version" in record.metadata_:
                props["model_version"] = str(record.metadata_["model_version"])

        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        await _upsert_object(collection, wv_uuid=wv_uuid, properties=props, vector=vector)
        logger.debug(
            "Upserted RecordEmbedding %s (record_id=%s)", wv_uuid, record.record_id
        )
        return wv_uuid

    async def remove_record_embedding(self, record_id: uuid.UUID) -> None:
        """Delete a RecordEmbedding document by record_id.

        No-ops if the document does not exist.
        """
        wv_uuid = record_weaviate_uuid(record_id)
        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)
        logger.debug("Removed RecordEmbedding for record_id=%s", record_id)

    # ------------------------------------------------------------------
    # Cluster snapshot management
    # ------------------------------------------------------------------

    async def sync_cluster(
        self,
        cluster_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Sync a cluster's materialised MEMBERSHIP state to Weaviate.

        Reads the MEMBERSHIP table from Postgres, fetches per-member
        vectors from RecordEmbedding in Weaviate, computes per-modality
        centroid vectors, and upserts a ClusterSnapshot document.

        If the cluster has no members with indexed vectors, the snapshot
        is still written so that the cluster is discoverable via metadata
        filters.  In that case the named vectors are omitted and searches
        over that modality will not return this cluster.

        Args:
            cluster_id: UUID of the cluster to sync.
            session: Active async SQLAlchemy session.
        """
        cluster = await Cluster.get(session, cluster_id)
        if cluster is None:
            logger.warning("sync_cluster called for unknown cluster_id=%s", cluster_id)
            return

        memberships = await Membership.get_for_cluster(session, cluster_id)

        # Fetch Record rows for all members in one round-trip.
        record_ids = {m.record_id for m in memberships}
        record_map: dict[uuid.UUID, Record] = {}
        if record_ids:
            result = await session.execute(
                select(Record).where(Record.record_id.in_(record_ids))
            )
            for rec in result.scalars().all():
                record_map[rec.record_id] = rec

        # Partition member record_ids by modality for vector fetching.
        face_record_ids = [
            m.record_id
            for m in memberships
            if record_map.get(m.record_id) is not None
            and record_map[m.record_id].record_type == RecordType.face_detection
            and record_map[m.record_id].embedding_id is not None
        ]
        name_record_ids = [
            m.record_id
            for m in memberships
            if record_map.get(m.record_id) is not None
            and record_map[m.record_id].record_type == RecordType.named_entity
            and record_map[m.record_id].embedding_id is not None
        ]

        face_centroid = await self._compute_centroid_from_weaviate(face_record_ids)
        name_centroid = await self._compute_centroid_from_weaviate(name_record_ids)

        # Count members per modality.
        face_count = sum(
            1 for m in memberships
            if record_map.get(m.record_id) is not None
            and record_map[m.record_id].record_type == RecordType.face_detection
        )
        named_entity_count = sum(
            1 for m in memberships
            if record_map.get(m.record_id) is not None
            and record_map[m.record_id].record_type == RecordType.named_entity
        )
        text_region_count = sum(
            1 for m in memberships
            if record_map.get(m.record_id) is not None
            and record_map[m.record_id].record_type == RecordType.text_region
        )

        props: dict[str, Any] = {
            "cluster_id": str(cluster_id),
            "cluster_role": cluster.cluster_role.value,
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
            wv_uuid,
            cluster_id,
            face_count,
            named_entity_count,
        )

    async def remove_cluster_snapshot(self, cluster_id: uuid.UUID) -> None:
        """Delete a ClusterSnapshot document.

        No-ops if the document does not exist.
        """
        wv_uuid = cluster_weaviate_uuid(cluster_id)
        collection = self._client.collections.get(CLUSTER_SNAPSHOT_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)
        logger.debug("Removed ClusterSnapshot for cluster_id=%s", cluster_id)

    async def sync_record_cluster_membership(
        self,
        record_id: uuid.UUID,
        cluster_id: uuid.UUID | None,
    ) -> None:
        """Update the cluster_id property on an existing RecordEmbedding.

        Used after a cluster membership change to keep the denormalised
        cluster_id on RecordEmbedding consistent with MEMBERSHIP.

        Args:
            record_id: The record whose membership changed.
            cluster_id: The new cluster_id, or None to clear membership.
        """
        wv_uuid = record_weaviate_uuid(record_id)
        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)
        props: dict[str, Any] = {}
        if cluster_id is not None:
            props["cluster_id"] = str(cluster_id)
        else:
            props["cluster_id"] = None
        try:
            await collection.data.update(uuid=wv_uuid, properties=props)
        except weaviate.exceptions.UnexpectedStatusCodeError as exc:
            if exc.status_code == 404:
                logger.debug(
                    "RecordEmbedding %s not found during membership sync (record_id=%s)",
                    wv_uuid,
                    record_id,
                )
            else:
                raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _compute_centroid_from_weaviate(
        self,
        record_ids: list[uuid.UUID],
    ) -> list[float] | None:
        """Fetch vectors from RecordEmbedding and return their centroid.

        Args:
            record_ids: List of record UUIDs to fetch vectors for.

        Returns:
            Centroid vector, or None if no records have indexed vectors.
        """
        if not record_ids:
            return None

        collection = self._client.collections.get(RECORD_EMBEDDING_COLLECTION)

        # Fetch each object by its deterministic Weaviate UUID and collect vectors.
        vectors: list[list[float]] = []
        for record_id in record_ids:
            wv_uuid = record_weaviate_uuid(record_id)
            try:
                obj = await collection.query.fetch_object_by_id(
                    uuid=wv_uuid,
                    include_vector=True,
                )
                if obj.vector:
                    # For un-named vector collections the key is "default"
                    raw = obj.vector.get("default")
                    if isinstance(raw, list) and raw and isinstance(raw[0], float):
                        vectors.append(cast(list[float], raw))
            except Exception:
                logger.debug(
                    "Failed to fetch vector for record_id=%s from Weaviate", record_id
                )

        return _centroid(vectors)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


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
    """Insert or replace a Weaviate object with the given UUID.

    Weaviate does not have native upsert semantics: insert raises HTTP 409
    on duplicate UUIDs.  We catch that error and fall back to replace().
    """
    try:
        await collection.data.insert(
            uuid=wv_uuid,
            properties=properties,
            vector=vector,
        )
    except weaviate.exceptions.UnexpectedStatusCodeError as exc:
        if exc.status_code == 409:
            # Object already exists — replace it entirely.
            await collection.data.replace(
                uuid=wv_uuid,
                properties=properties,
                vector=vector,
            )
        else:
            raise
