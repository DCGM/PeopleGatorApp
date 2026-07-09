"""Vector sync service for annotation and identity mirrors in Weaviate.

This service mirrors relational annotation rows into dedicated Weaviate
collections (Name, Description, Information, Mention, Face, DocumentMention)
and maintains IdentitySnapshot as a derived read model.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from typing import Any

import weaviate.exceptions
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from weaviate import WeaviateAsyncClient

from people_gator_api.models.annotation.description import Description
from people_gator_api.models.annotation.document_mention import DocumentMention
from people_gator_api.models.annotation.face import Face
from people_gator_api.models.annotation.information import Information
from people_gator_api.models.annotation.mention import Mention
from people_gator_api.models.annotation.name import Name
from people_gator_api.models.enums import AnnotationType
from people_gator_api.models.identity import Identity
from people_gator_api.services.vector_service.schema import (
    DESCRIPTION_COLLECTION,
    DOCUMENT_MENTION_COLLECTION,
    DOCUMENT_MENTION_INFORMATION_VECTOR,
    DOCUMENT_MENTION_NAME_VECTOR,
    FACE_COLLECTION,
    FACE_VECTOR,
    IDENTITY_SNAPSHOT_COLLECTION,
    INFORMATION_COLLECTION,
    MENTION_COLLECTION,
    NAME_COLLECTION,
    NAME_VECTOR,
    collection_for_annotation_type,
)

logger = logging.getLogger(__name__)


PropertyValue = str | float | int | None

_VECTOR_OBJECT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
_IDENTITY_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")


def vector_object_uuid(collection_name: str, row_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for mirrored annotation row documents."""
    return uuid.uuid5(_VECTOR_OBJECT_NS, f"{collection_name}:{row_id}")


def annotation_weaviate_uuid(
    annotation_type: AnnotationType,
    annotation_id: uuid.UUID,
) -> uuid.UUID:
    """Backward-compatible UUID helper for annotation objects."""
    collection_name = collection_for_annotation_type(annotation_type)
    return vector_object_uuid(collection_name, annotation_id)


def identity_weaviate_uuid(identity_id: uuid.UUID) -> uuid.UUID:
    """Deterministic Weaviate UUID for an IdentitySnapshot document."""
    return uuid.uuid5(_IDENTITY_NS, f"identity:{identity_id}")


def _annotation_id_field(annotation_type: AnnotationType) -> str:
    if annotation_type is AnnotationType.person_name:
        return "name_id"
    if annotation_type is AnnotationType.description:
        return "description_id"
    if annotation_type is AnnotationType.information:
        return "information_id"
    if annotation_type is AnnotationType.mention:
        return "mention_id"
    if annotation_type is AnnotationType.face:
        return "detection_id"
    return "document_mention_id"


def _supports_identity_update(annotation_type: AnnotationType) -> bool:
    return annotation_type in {
        AnnotationType.person_name,
        AnnotationType.description,
        AnnotationType.face,
        AnnotationType.document_mention,
    }


class IdentitySyncService:
    """Async service that mirrors Postgres state into Weaviate."""

    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def upsert_name(
        self,
        *,
        name_id: uuid.UUID,
        name: str,
        source_id: uuid.UUID,
        identity_id: uuid.UUID,
        vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "name_id": str(name_id),
            "name": name,
            "source_id": str(source_id),
            "identity_id": str(identity_id),
        }
        return await self._upsert_collection_object(
            collection_name=NAME_COLLECTION,
            row_id=name_id,
            properties=props,
            vector=vector,
        )

    async def remove_name(self, name_id: uuid.UUID) -> None:
        await self._remove_collection_object(NAME_COLLECTION, name_id)

    async def upsert_description(
        self,
        *,
        description_id: uuid.UUID,
        text: str,
        language: str,
        source_id: uuid.UUID,
        identity_id: uuid.UUID,
        vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "description_id": str(description_id),
            "text": text,
            "language": language,
            "source_id": str(source_id),
            "identity_id": str(identity_id),
        }
        return await self._upsert_collection_object(
            collection_name=DESCRIPTION_COLLECTION,
            row_id=description_id,
            properties=props,
            vector=vector,
        )

    async def remove_description(self, description_id: uuid.UUID) -> None:
        await self._remove_collection_object(DESCRIPTION_COLLECTION, description_id)

    async def upsert_information(
        self,
        *,
        information_id: uuid.UUID,
        text: str,
        source_id: uuid.UUID,
        model_agent_id: uuid.UUID,
        vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "information_id": str(information_id),
            "text": text,
            "source_id": str(source_id),
            "model_agent_id": str(model_agent_id),
        }
        return await self._upsert_collection_object(
            collection_name=INFORMATION_COLLECTION,
            row_id=information_id,
            properties=props,
            vector=vector,
        )

    async def remove_information(self, information_id: uuid.UUID) -> None:
        await self._remove_collection_object(INFORMATION_COLLECTION, information_id)

    async def upsert_mention(
        self,
        *,
        mention_id: uuid.UUID,
        text: str,
        offset_start: int,
        offset_end: int,
        polygons: list[dict[str, list[dict[str, float]]]] | None,
        confidence: float,
        source_id: uuid.UUID,
        model_agent_id: uuid.UUID,
        vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "mention_id": str(mention_id),
            "text": text,
            "offset_start": offset_start,
            "offset_end": offset_end,
            "confidence": confidence,
            "polygons_json": (
                json.dumps(polygons, separators=(",", ":"))
                if polygons is not None
                else None
            ),
            "source_id": str(source_id),
            "model_agent_id": str(model_agent_id),
        }
        return await self._upsert_collection_object(
            collection_name=MENTION_COLLECTION,
            row_id=mention_id,
            properties=props,
            vector=vector,
        )

    async def remove_mention(self, mention_id: uuid.UUID) -> None:
        await self._remove_collection_object(MENTION_COLLECTION, mention_id)

    async def upsert_face(
        self,
        *,
        detection_id: uuid.UUID,
        source_id: uuid.UUID,
        model_agent_id: uuid.UUID,
        identity_id: uuid.UUID,
        confidence: float,
        bounding_box: dict[str, int],
        keypoints: list[dict[str, float | str]],
        vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "detection_id": str(detection_id),
            "source_id": str(source_id),
            "model_agent_id": str(model_agent_id),
            "identity_id": str(identity_id),
            "confidence": confidence,
            "bbox_x": int(bounding_box["x"]),
            "bbox_y": int(bounding_box["y"]),
            "bbox_width": int(bounding_box["width"]),
            "bbox_height": int(bounding_box["height"]),
            "keypoints_json": json.dumps(keypoints, separators=(",", ":")),
        }
        return await self._upsert_collection_object(
            collection_name=FACE_COLLECTION,
            row_id=detection_id,
            properties=props,
            vector=vector,
        )

    async def remove_face(self, detection_id: uuid.UUID) -> None:
        await self._remove_collection_object(FACE_COLLECTION, detection_id)

    async def upsert_document_mention(
        self,
        *,
        document_mention_id: uuid.UUID,
        name: str,
        information: str,
        model_agent_id: uuid.UUID,
        source_id: uuid.UUID,
        identity_id: uuid.UUID,
        name_vector: list[float] | None,
        information_vector: list[float] | None,
    ) -> uuid.UUID:
        props = {
            "document_mention_id": str(document_mention_id),
            "name": name,
            "information": information,
            "model_agent_id": str(model_agent_id),
            "source_id": str(source_id),
            "identity_id": str(identity_id),
        }
        vectors: dict[str, list[float]] = {}
        if name_vector is not None:
            vectors[DOCUMENT_MENTION_NAME_VECTOR] = name_vector
        if information_vector is not None:
            vectors[DOCUMENT_MENTION_INFORMATION_VECTOR] = information_vector

        return await self._upsert_collection_object(
            collection_name=DOCUMENT_MENTION_COLLECTION,
            row_id=document_mention_id,
            properties=props,
            vector=vectors if vectors else None,
        )

    async def remove_document_mention(self, document_mention_id: uuid.UUID) -> None:
        await self._remove_collection_object(DOCUMENT_MENTION_COLLECTION, document_mention_id)

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
        """Backward-compatible generic upsert command for single-vector annotations."""
        collection_name = collection_for_annotation_type(annotation_type)
        id_field = _annotation_id_field(annotation_type)

        properties: dict[str, str | float | int] = {
            id_field: str(annotation_id),
            "source_id": str(source_id),
        }
        if model_agent_id is not None:
            properties["model_agent_id"] = str(model_agent_id)
        if confidence is not None:
            properties["confidence"] = confidence
        if identity_id is not None and _supports_identity_update(annotation_type):
            properties["identity_id"] = str(identity_id)

        row_uuid = vector_object_uuid(collection_name, annotation_id)
        collection = self._client.collections.get(collection_name)
        await _upsert_object(
            collection=collection,
            wv_uuid=row_uuid,
            properties=properties,
            vector=vector,
        )
        return row_uuid

    async def remove_annotation_embedding(
        self,
        annotation_type: AnnotationType,
        annotation_id: uuid.UUID,
    ) -> None:
        """Backward-compatible generic remove command."""
        collection_name = collection_for_annotation_type(annotation_type)
        await self._remove_collection_object(collection_name, annotation_id)

    async def sync_identity(
        self,
        identity_id: uuid.UUID,
        session: AsyncSession,
    ) -> None:
        """Sync an identity snapshot document from relational source state."""
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
        mentions = list(
            (
                await session.execute(select(Mention).where(Mention.source_id.in_([f.source_id for f in faces])))
            )
            .scalars()
            .all()
        ) if faces else []
        information = list(
            (
                await session.execute(
                    select(Information).where(Information.source_id.in_([f.source_id for f in faces]))
                )
            )
            .scalars()
            .all()
        ) if faces else []
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

        face_centroid = await self._compute_centroid_from_collection(
            collection_name=FACE_COLLECTION,
            row_ids=[item.detection_id for item in faces],
        )
        name_centroid = await self._compute_centroid_from_collection(
            collection_name=NAME_COLLECTION,
            row_ids=[item.name_id for item in names],
        )

        props: dict[str, str | int] = {
            "identity_id": str(identity_id),
            "face_count": len(faces),
            "mention_count": len(mentions),
            "information_count": len(information),
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
            collection=collection,
            wv_uuid=wv_uuid,
            properties=props,
            vector=named_vectors if named_vectors else None,
        )

    async def remove_identity_snapshot(self, identity_id: uuid.UUID) -> None:
        wv_uuid = identity_weaviate_uuid(identity_id)
        collection = self._client.collections.get(IDENTITY_SNAPSHOT_COLLECTION)
        await collection.data.delete_by_id(wv_uuid)

    async def sync_annotation_identity_link(
        self,
        annotation_type: AnnotationType,
        annotation_id: uuid.UUID,
        identity_id: uuid.UUID | None,
    ) -> None:
        """Update identity_id property on mirrored annotation documents."""
        if not _supports_identity_update(annotation_type):
            logger.debug(
                "Annotation type %s does not support identity_id updates",
                annotation_type.value,
            )
            return

        collection_name = collection_for_annotation_type(annotation_type)
        row_uuid = vector_object_uuid(collection_name, annotation_id)
        collection = self._client.collections.get(collection_name)

        props = {
            "identity_id": str(identity_id) if identity_id is not None else None,
        }
        try:
            await collection.data.update(uuid=row_uuid, properties=props)
        except weaviate.exceptions.UnexpectedStatusCodeError as exc:
            if exc.status_code == 404:
                logger.debug(
                    "Object %s not found in %s during identity link sync",
                    row_uuid,
                    collection_name,
                )
            else:
                raise

    async def _compute_centroid_from_collection(
        self,
        *,
        collection_name: str,
        row_ids: list[uuid.UUID],
    ) -> list[float] | None:
        if not row_ids:
            return None

        collection = self._client.collections.get(collection_name)
        vectors: list[list[float]] = []
        for row_id in row_ids:
            row_uuid = vector_object_uuid(collection_name, row_id)
            try:
                obj = await collection.query.fetch_object_by_id(
                    uuid=row_uuid,
                    include_vector=True,
                )
            except Exception:
                logger.debug(
                    "Failed to fetch vector for %s row %s",
                    collection_name,
                    row_id,
                )
                continue

            vector = _extract_primary_vector(obj.vector)
            if vector is not None:
                vectors.append(vector)

        return _centroid(vectors)

    async def _upsert_collection_object(
        self,
        *,
        collection_name: str,
        row_id: uuid.UUID,
        properties: Mapping[str, PropertyValue],
        vector: list[float] | dict[str, list[float]] | None,
    ) -> uuid.UUID:
        row_uuid = vector_object_uuid(collection_name, row_id)
        collection = self._client.collections.get(collection_name)
        await _upsert_object(
            collection=collection,
            wv_uuid=row_uuid,
            properties=properties,
            vector=vector,
        )
        return row_uuid

    async def _remove_collection_object(self, collection_name: str, row_id: uuid.UUID) -> None:
        row_uuid = vector_object_uuid(collection_name, row_id)
        collection = self._client.collections.get(collection_name)
        await collection.data.delete_by_id(row_uuid)


def _extract_primary_vector(
    raw_vector: list[float] | dict[str, list[float] | list[list[float]]] | None,
) -> list[float] | None:
    if raw_vector is None:
        return None
    if isinstance(raw_vector, list):
        return raw_vector if raw_vector and isinstance(raw_vector[0], float) else None

    default_vector = raw_vector.get("default")
    if isinstance(default_vector, list) and default_vector:
        scalar_values = [value for value in default_vector if isinstance(value, float)]
        if len(scalar_values) == len(default_vector):
            return scalar_values

    if raw_vector:
        first_value = next(iter(raw_vector.values()))
        if first_value:
            scalar_values = [value for value in first_value if isinstance(value, float)]
            if len(scalar_values) == len(first_value):
                return scalar_values

    return None


def _centroid(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None

    dimension = len(vectors[0])
    n_vectors = len(vectors)
    return [sum(v[i] for v in vectors) / n_vectors for i in range(dimension)]


async def _upsert_object(
    collection: Any,  # Weaviate collection types are dynamic/generic and not fully protocol-friendly.
    *,
    wv_uuid: uuid.UUID,
    properties: Mapping[str, PropertyValue],
    vector: list[float] | dict[str, list[float]] | None,
) -> None:
    data = dict(properties)
    try:
        await collection.data.insert(
            uuid=wv_uuid,
            properties=data,
            vector=vector,
        )
    except weaviate.exceptions.UnexpectedStatusCodeError as exc:
        if exc.status_code == 409:
            await collection.data.replace(
                uuid=wv_uuid,
                properties=data,
                vector=vector,
            )
        else:
            raise
