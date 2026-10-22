from __future__ import annotations

import uuid
from people_gator_api.persistence.entity_links import create_link_state, link_transition, apply_link
from people_gator_api.schemas.missing import is_missing
import numpy as np
from collections.abc import Sequence

from sqlalchemy import (
    or_,
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
    face_text_candidates,
    search_face_scores,
    commit,
    ensure_ids,
    cursor_fingerprint,
    fuse_scores,
    search_page,
    face_response,
    face_filters,
    validate_face_embeddings,
)

from people_gator_api.schemas.sorting import RELEVANCE, SortDirection
from .sorting import (
    Builders,
    SortKey,
    SortSpec,
    after_predicate,
    annotation_builders,
    build_spec,
    decode_keyset,
    keyset_page,
    order_by,
    sort_columns,
    with_sort_joins,
    sort_ranked,
)
from .touch import touch_entities, touch_sources, lock_annotation_graph, creation_values, touch_values, apply_touch
from .search_resolution import resolve_entity_search


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
        rows = await self._session.scalars(statement.execution_options(populate_existing=True))
        return {row.id: row for row in rows.unique().all()}

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        face = (await self._load_many([detection_id])).get(detection_id)
        return face_response(face) if face is not None else None

    @staticmethod
    def _sort_spec(field: str | None, direction: SortDirection) -> SortSpec:
        builders: Builders = {
            **annotation_builders(Face),
            "confidence": lambda desc: [SortKey(Face.confidence, "number", desc)],
        }
        return build_spec(field, direction, Face.id, builders, "detection_id")

    async def list(self, query: FaceListRequest) -> FaceListResponse:
        filters = face_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        spec = self._sort_spec(*query.effective_sort())
        after = decode_keyset(query.cursor, spec, fingerprint)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(select(func.count(Face.id)).where(*filters))
                or 0
            )
        if query.limit == 0:
            return FaceListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if after is not None:
            page_filters.append(after_predicate(spec, after))
        result = await self._session.execute(
            with_sort_joins(select(Face, *sort_columns(spec)), spec)
            .options(selectinload(Face.embeddings))
            .where(*page_filters)
            .order_by(*order_by(spec))
            .limit(query.limit + 1)
        )
        rows = [(row[0], tuple(row[1:])) for row in result.all()]
        page, cursor = keyset_page(rows, query.limit, spec, fingerprint)
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
            **creation_values(context),
            **touch_values(context),
            source_id=payload.source_id,
            entity_id=missing_to_none(payload.entity_id),
            entity_link_state=create_link_state(payload),
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
        await lock_annotation_graph(self._session)
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
        await touch_sources(self._session, [item.source_id for item in payloads], context)
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
        await lock_annotation_graph(self._session)
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
        transitions = {c.detection_id: link_transition(faces[c.detection_id], c, context) for c in commands if c.detection_id in faces}
        touched: set[uuid.UUID | None] = set()
        sources: set[uuid.UUID] = set()
        for command in commands:
            face = faces.get(command.detection_id)
            if face is None:
                continue
            old_entity_id = face.entity_id
            values = transitions[command.detection_id]
            link_changed = values != (face.entity_id, face.entity_link_state, face.entity_link_verified_by_user_id, face.entity_link_verified_at)
            old_embeddings = {item.model_id: list(item.embedding) for item in face.embeddings}
            embeddings_changed = any(
                item.model_identifier not in old_embeddings
                or not np.array_equal(
                    np.asarray(old_embeddings[item.model_identifier], dtype=np.float32),
                    np.asarray(item.vector, dtype=np.float32),
                )
                for item in (missing_to_none(command.embeddings) or [])
            )
            apply_link(face, values)
            if embeddings_changed:
                self._apply_embeddings(face, command)
            if link_changed or embeddings_changed:
                apply_touch(face, context)
                touched.update([old_entity_id, face.entity_id])
                sources.add(face.source_id)
        await touch_entities(self._session, touched, context)
        await touch_sources(self._session, sources, context)
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
        await lock_annotation_graph(self._session)
        removed = list(await self._session.execute(
            delete(ImageOccurrence).where(ImageOccurrence.id.in_(unique), ImageOccurrence.occurrence_type == "face")
            .returning(ImageOccurrence.entity_id, ImageOccurrence.source_id)
        ))
        await touch_entities(self._session, [row.entity_id for row in removed], context)
        await touch_sources(self._session, [row.source_id for row in removed], context)
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
                .where(*filters, Face.id.in_(face_text_candidates(term, filters)))
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
        fingerprint = cursor_fingerprint(query)
        query = await resolve_entity_search(self._session, query)
        filters = face_filters(query.filter_)
        if query.query.entity_id is not None and query.query.exclude_reference_face_id:
            filters.append(or_(Face.entity_id.is_(None), Face.entity_id != query.query.entity_id))
        ranked = fuse_scores(
            await self._text_scores(query, filters),
            await self._face_scores(query, filters),
        )
        field, direction = query.effective_sort()
        spec = None if field == RELEVANCE else self._sort_spec(field, direction)
        values: dict[uuid.UUID, tuple[object, ...]] = {}
        if spec is not None and ranked:
            rows = await self._session.execute(
                with_sort_joins(select(Face.id, *sort_columns(spec)), spec).where(
                    Face.id.in_([item[0] for item in ranked])
                )
            )
            values = {row[0]: tuple(row[1:]) for row in rows.all()}
        ranked = sort_ranked(ranked, spec, direction, values)
        page, cursor = search_page(
            ranked,
            query.cursor,
            query.limit,
            fingerprint,
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
