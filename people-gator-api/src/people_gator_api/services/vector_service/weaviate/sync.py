"""Identity sync service — synchronises Postgres LINK_CONSENSUS rows to Weaviate.

IdentitySyncService maintains two Weaviate collections:

AnnotationEmbedding
    One document per (annotation_type, annotation_id) pair.  Callers are
    responsible for supplying the pre-computed embedding vector at upsert
    time; this service does not generate embeddings.  The Weaviate UUID
    assigned to each document is deterministic (UUID5 from annotation_type
    + annotation_id) and requires no back-reference stored on the annotation
    tables.

IdentitySnapshot
    One document per identity.  Synced by reading the materialised
    LINK_CONSENSUS 'include' rows from Postgres, fetching the per-annotation
    vectors from AnnotationEmbedding, computing per-modality centroid
    vectors, and upserting an IdentitySnapshot document with named vectors
    for face and name modalities.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, cast

import weaviate.exceptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weaviate import WeaviateAsyncClient

from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.document_mention import DocumentMention
from people_gator_api.models.annotation.face import Face
from people_gator_api.models.annotation.name import Name
from people_gator_api.models.enums import AnnotationType
from people_gator_api.models.identity import Identity
from people_gator_api.services.vector_service.weaviate.schema import (
    ANNOTATION_EMBEDDING_COLLECTION,
    FACE_VECTOR,
    IDENTITY_SNAPSHOT_COLLECTION,
    NAME_VECTOR,
)

logger = logging.getLogger(__name__)

_ANNOTATION_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_IDENTITY_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def annotation_weaviate_uuid(
    annotation_type: AnnotationType,
    annotation_id: uuid.UUID,
) -> uuid.UUID:
    """Deterministic Weaviate UUID for an AnnotationEmbedding document."""
    return uuid.uuid5(_ANNOTATION_NS, f"annotation:{annotation_type.value}:{annotation_id}")


def identity_weaviate_uuid(identity_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for an IdentitySnapshot document."""
    return uuid.uuid5(_IDENTITY_NS, f"identity:{identity_id}")


class IdentitySyncService:
    """Async service that mirrors Postgres identity state into Weaviate."""

    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def upsert_annotation_embedding(
        self,
        annotation_type: AnnotationType,
        annotation_id: uuid.UUID,
        vector: list[float],
        *,
        source_id: uuid.UUID,
        model_agent_id: uuid.UUID | None = None,
        confidence: float | None = None,
        identity_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Upsert an AnnotationEmbedding document and return its Weaviate UUID."""
        wv_uuid = annotation_weaviate_uuid(annotation_type, annotation_id)
        props: dict[str, Any] = {
            "annotation_type": annotation_type.value,
            "annotation_id": str(annotation_id),
            "source_id": str(source_id),
        }
        if identity_id is not None:
            props["identity_id"] = str(identity_id)
        if model_agent_id is not None:
            props["model_agent_id"] = str(model_agent_id)
        if confidence is not None:
            props["confidence"] = confidence

        collection = self._client.collections.get(ANNOTATION_EMBEDDING_COLLECTION)
        await _upsert_object(collection, wv_uuid=wv_uuid, properties=props, vector=vector)
        logger.debug(
            "Upserted AnnotationEmbedding %s (annotation_type=%s, annotation_id=%s)",
            wv_uuid, annotation_type.value, annotation_id,
        )
        return wv_uuid

    async def remove_annotation_embedding(
        self,
        annotation_type: AnnotationType,
        annotation_id: uuid.UUID,
    ) -> None:
        """Delete an AnnotationEmbedding document. No-ops if not found."""
        wv_uuid = annotation_weaviate_uuid(annotation_type, annotation_id)
        collection = self._client.collections.get(ANNOTATION_EMBEDDING_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)

    async def sync_identity(
        self,
        identity_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Sync an identity's materialised LINK_CONSENSUS state to Weaviate.

        Reads simplified identity-linked entities for this identity, fetches
        per-annotation vectors from AnnotationEmbedding, computes per-modality
        centroid vectors, and upserts an IdentitySnapshot document.
        """
        identity = await Identity.get(session, identity_id)
        if identity is None:
            logger.warning("sync_identity called for unknown identity_id=%s", identity_id)
            return

        faces = list(
            (
                await session.execute(select(Face).where(Face.identity_id == identity_id))
            )
            .scalars()
            .all()
        )
        descriptions = list(
            (
                await session.execute(
                    select(Description).where(Description.identity_id == identity_id)
                )
            )
            .scalars()
            .all()
        )
        names = list(
            (
                await session.execute(select(Name).where(Name.identity_id == identity_id))
            )
            .scalars()
            .all()
        )
        document_mentions = list(
            (
                await session.execute(
                    select(DocumentMention).where(DocumentMention.identity_id == identity_id)
                )
            )
            .scalars()
            .all()
        )

        face_centroid = await self._compute_centroid_from_weaviate(
            AnnotationType.face,
            [item.detection_id for item in faces],
        )
        name_centroid = await self._compute_centroid_from_weaviate(
            AnnotationType.person_name,
            [item.name_id for item in names],
        )

        props: dict[str, Any] = {
            "identity_id": str(identity_id),
            "face_count": len(faces),
            "mention_count": 0,
            "information_count": 0,
            "document_mention_count": len(document_mentions),
            "description_count": len(descriptions),
            "name_count": len(names),
        }

        named_vectors: dict[str, list[float]] = {}
        if face_centroid is not None:
            named_vectors[FACE_VECTOR] = face_centroid
        if name_centroid is not None:
            named_vectors[NAME_VECTOR] = name_centroid

        wv_uuid = identity_weaviate_uuid(identity_id)
        collection = self._client.collections.get(IDENTITY_SNAPSHOT_COLLECTION)
        await _upsert_object(
            collection,
            wv_uuid=wv_uuid,
            properties=props,
            vector=named_vectors if named_vectors else None,
        )
        logger.info(
            "Synced IdentitySnapshot %s (identity_id=%s, face=%d, name=%d)",
            wv_uuid,
            identity_id,
            len(faces),
            len(names),
        )

    async def remove_identity_snapshot(self, identity_id: uuid.UUID) -> None:
        """Delete an IdentitySnapshot document. No-ops if not found."""
        wv_uuid = identity_weaviate_uuid(identity_id)
        collection = self._client.collections.get(IDENTITY_SNAPSHOT_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)

    async def sync_annotation_identity_link(
        self,
        annotation_type: AnnotationType,
        annotation_id: uuid.UUID,
        identity_id: uuid.UUID | None,
    ) -> None:
        """Update the identity_id property on an existing AnnotationEmbedding."""
        wv_uuid = annotation_weaviate_uuid(annotation_type, annotation_id)
        collection = self._client.collections.get(ANNOTATION_EMBEDDING_COLLECTION)
        props: dict[str, Any] = {
            "identity_id": str(identity_id) if identity_id is not None else None,
        }
        try:
            await collection.data.update(uuid=wv_uuid, properties=props)
        except weaviate.exceptions.UnexpectedStatusCodeError as exc:
            if exc.status_code == 404:
                logger.debug(
                    "AnnotationEmbedding %s not found during identity link sync (annotation_type=%s, annotation_id=%s)",
                    wv_uuid, annotation_type.value, annotation_id,
                )
            else:
                raise

    async def _compute_centroid_from_weaviate(
        self,
        annotation_type: AnnotationType,
        annotation_ids: list[uuid.UUID],
    ) -> list[float] | None:
        """Fetch vectors from AnnotationEmbedding and return their centroid."""
        if not annotation_ids:
            return None

        collection = self._client.collections.get(ANNOTATION_EMBEDDING_COLLECTION)
        vectors: list[list[float]] = []
        for ann_id in annotation_ids:
            wv_uuid = annotation_weaviate_uuid(annotation_type, ann_id)
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
                    "Failed to fetch vector for annotation_type=%s annotation_id=%s from Weaviate",
                    annotation_type.value, ann_id,
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
