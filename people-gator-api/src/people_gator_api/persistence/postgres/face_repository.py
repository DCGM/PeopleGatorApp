from __future__ import annotations

import uuid
import numpy as np
from collections.abc import Sequence

from sqlalchemy import (
    ColumnElement,
    delete,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from people_gator_api.persistence.contracts import (
    FaceRepository,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FaceListRequest,
    FaceListResponse,
    FacePatchBatchItem,
    FacePatchRequest,
    FaceResponse,
)
from people_gator_api.schemas.missing import (
    is_missing,
    missing_to_none,
)
from people_gator_api.schemas.search import (
    FoundFace,
    SearchFacesRequest,
    SearchFacesResultListResponse,
)
from people_gator_api.persistence.postgres.models import (
    Alias,
    Entity,
    Face,
    FaceEmbedding as FaceEmbeddingRow,
    ImageOccurrence,
    Source,
    User,
)


from people_gator_api.persistence.postgres.utils import (
    aggregate_scores,
    search_face_scores,
    commit,
    ensure_ids,
    validate_cursor,
    cursor_fingerprint,
    decode_cursor,
    next_cursor,
    fuse_scores,
    search_page,
    face_response,
    face_filters,
    validate_face_embeddings,
)

from .touch import touch_entities

class PostgresFaceRepository(FaceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID], *, lock: bool = False) -> dict[uuid.UUID, Face]:
        if not ids:
            return {}
        statement = select(Face).where(Face.id.in_(ids)).options(selectinload(Face.embeddings))
        if lock:
            statement = statement.order_by(Face.id).with_for_update()
        rows = await self._session.scalars(statement)
        return {row.id: row for row in rows.unique().all()}

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        face = (await self._load_many([detection_id])).get(detection_id)
        return face_response(face) if face is not None else None

    async def list(self, query: FaceListRequest) -> FaceListResponse:
        filters = face_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, Face, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(select(func.count(Face.id)).where(*filters))
                or 0
            )
        if query.limit == 0:
            return FaceListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Face.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(Face)
                .options(selectinload(Face.embeddings))
                .where(*page_filters)
                .order_by(Face.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = next_cursor(rows, query.limit, Face.id, fingerprint)
        return FaceListResponse(
            items=[face_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: FaceCreateRequest, context: GenericActor) -> Face:
        embeddings = missing_to_none(payload.embeddings)
        face = Face(
            source_id=payload.source_id,
            entity_id=missing_to_none(payload.entity_id),
            user_id=context.user_id,
            identifier=missing_to_none(payload.identifier),
            confidence=payload.confidence,
            roi=payload.bounding_box.model_dump(),
            keypoints=[[item.x, item.y] for item in payload.keypoints],
            keypoint_types=[item.type for item in payload.keypoints],
        )
        face.embeddings = []
        if embeddings:
            face.embeddings = [
                FaceEmbeddingRow(
                    model_id=value.model_identifier,
                    embedding=list(value.vector),
                )
                for value in embeddings
            ]
        return face

    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        if not payloads:
            return []
        await ensure_ids(self._session, User, [context.user_id], "actor user")
        await ensure_ids(
            self._session, Source, [item.source_id for item in payloads], "face source"
        )
        entity_ids = [
            entity_id
            for item in payloads
            if (entity_id := missing_to_none(item.entity_id)) is not None
        ]
        await ensure_ids(
            self._session,
            Entity,
            entity_ids,
            "face entity",
        )
        await validate_face_embeddings(
            self._session,
            (
                embedding
                for payload in payloads
                for embedding in (missing_to_none(payload.embeddings) or [])
            ),
        )
        faces = [self._new(payload, context) for payload in payloads]
        self._session.add_all(faces)
        await touch_entities(self._session, entity_ids, context)
        await commit(self._session, "face create violates a persistence constraint")
        return [face_response(face) for face in faces]

    @staticmethod
    def _apply_embeddings(face: Face, payload: FacePatchRequest) -> None:
        embeddings = missing_to_none(payload.embeddings)
        if not embeddings:
            return
        existing = {embedding.model_id: embedding for embedding in face.embeddings}
        for value in embeddings:
            embedding = existing.get(value.model_identifier)
            if embedding is None:
                face.embeddings.append(
                    FaceEmbeddingRow(
                        model_id=value.model_identifier,
                        embedding=list(value.vector),
                    )
                )
            else:
                embedding.embedding = list(value.vector)

    async def patch(
        self,
        detection_id: uuid.UUID,
        payload: FacePatchRequest,
        context: GenericActor,
    ) -> FaceResponse | None:
        command = FacePatchBatchItem(detection_id=detection_id, **payload.model_dump())
        return (await self.patch_batch([command], context))[0]

    async def patch_batch(
        self,
        commands: Sequence[FacePatchBatchItem],
        context: GenericActor,
    ) -> list[FaceResponse | None]:
        ids = [command.detection_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("face patch batch requires unique object IDs")
        if not commands:
            return []
        await ensure_ids(self._session, User, [context.user_id], "actor user")
        entity_ids = [
            entity_id
            for command in commands
            if not is_missing(command.entity_id)
            and (entity_id := command.entity_id) is not None
        ]
        await ensure_ids(
            self._session,
            Entity,
            entity_ids,
            "face entity",
        )
        await validate_face_embeddings(
            self._session,
            (
                embedding
                for command in commands
                for embedding in (missing_to_none(command.embeddings) or [])
            ),
        )
        faces = await self._load_many(ids, lock=True)
        touched: set[uuid.UUID | None] = set()
        for command in commands:
            face = faces.get(command.detection_id)
            if face is None:
                continue
            old_entity_id = face.entity_id
            reassigned = not is_missing(command.entity_id) and face.entity_id != command.entity_id
            old_embeddings = {item.model_id: list(item.embedding) for item in face.embeddings}
            embeddings_changed = any(
                item.model_identifier not in old_embeddings
                or not np.array_equal(
                    np.asarray(old_embeddings[item.model_identifier], dtype=np.float32),
                    np.asarray(item.vector, dtype=np.float32),
                )
                for item in (missing_to_none(command.embeddings) or [])
            )
            if not is_missing(command.entity_id):
                face.entity_id = command.entity_id
            if embeddings_changed:
                self._apply_embeddings(face, command)
            if reassigned or embeddings_changed:
                touched.update([old_entity_id, face.entity_id])
        await touch_entities(self._session, touched, context)
        await commit(self._session, "face patch violates a persistence constraint")
        return [
            face_response(face) if (face := faces.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, detection_id: uuid.UUID, *, context: GenericActor) -> bool:
        return bool(await self.delete_batch([detection_id], context=context))

    async def delete_batch(self, detection_ids: Sequence[uuid.UUID], *, context: GenericActor) -> int:
        unique = list(dict.fromkeys(detection_ids))
        if not unique:
            return 0
        removed = list(await self._session.scalars(
            delete(ImageOccurrence).where(ImageOccurrence.id.in_(unique), ImageOccurrence.occurrence_type == "face")
            .returning(ImageOccurrence.entity_id)
        ))
        await touch_entities(self._session, removed, context)
        await commit(self._session, "face delete failed")
        return len(removed)

    async def _text_scores(
        self, query: SearchFacesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            score = func.greatest(
                func.similarity(func.coalesce(Face.identifier, ""), term),
                func.similarity(func.coalesce(Entity.name, ""), term),
                func.coalesce(func.max(func.similarity(Alias.name, term)), 0.0),
            )
            rows = await self._session.execute(
                select(Face.id, score.label("score"))
                .outerjoin(Entity, Entity.id == Face.entity_id)
                .outerjoin(Alias, Alias.entity_id == Entity.id)
                .where(*filters)
                .group_by(Face.id, Entity.id)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return aggregate_scores(collected, query.query.score_aggregation)

    async def _face_scores(
        self, query: SearchFacesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        return await search_face_scores(
            session=self._session,
            target=Face,
            face_ids=face_ids,
            model_stub=query.query.face_embedding_model,
            filters=filters,
            exclude_reference_faces=query.query.exclude_reference_face_id,
            aggregation=query.query.score_aggregation,
        )

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        filters = face_filters(query.filter_)
        ranked = fuse_scores(
            await self._text_scores(query, filters),
            await self._face_scores(query, filters),
        )
        page, cursor = search_page(
            ranked,
            query.cursor,
            query.limit,
            cursor_fingerprint(query),
        )
        faces = await self._load_many([item[0] for item in page])
        items = [
            FoundFace(
                **face_response(faces[item_id]).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchFacesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=len(ranked) if query.return_total_count else None,
            cursor=cursor,
        )
