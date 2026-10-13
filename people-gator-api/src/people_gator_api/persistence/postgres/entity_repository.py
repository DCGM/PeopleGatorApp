from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, cast as type_cast

from sqlalchemy import (
    ColumnElement,
    delete,
    func,
    select,
    update,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from people_gator_api.persistence.contracts import (
    EntityRepository,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityListRequest,
    EntityListResponse,
    EntityMergeBatchResponse,
    EntityMergeTargetPatch,
    EntityPatchBatchItem,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.schemas.missing import (
    is_missing,
    missing_to_none,
)
from people_gator_api.schemas.search import (
    FoundEntity,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
)
from people_gator_api.persistence.postgres.models import (
    Alias,
    Entity,
    ImageOccurrence,
    TextMention,
    User,
)
from people_gator_api.persistence.postgres.utils import (
    cursor_fingerprint,
    decode_cursor,
    search_page,
    validate_cursor,
    next_cursor,
    entity_text_candidates,
    entity_filters,
    entity_response,
    aggregate_scores,
    ensure_ids,
    commit,
    search_face_scores,
    fuse_scores,
)

from .touch import touch_values

class PostgresEntityRepository(EntityRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID], *, lock: bool = False) -> dict[uuid.UUID, Entity]:
        if not ids:
            return {}
        statement = select(Entity).where(Entity.id.in_(ids)).options(selectinload(Entity.aliases))
        if lock:
            statement = statement.order_by(Entity.id).with_for_update()
        rows = await self._session.scalars(statement)
        return {row.id: row for row in rows.unique().all()}

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        entity = (await self._load_many([entity_id])).get(entity_id)
        return entity_response(entity) if entity is not None else None

    async def list(self, query: EntityListRequest) -> EntityListResponse:
        filters = entity_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, Entity, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(
                    select(func.count(Entity.id)).where(*filters)
                )
                or 0
            )
        if query.limit == 0:
            return EntityListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(Entity.id > cursor_id)
        rows = list(
            (
                await self._session.scalars(
                    select(Entity)
                    .where(*page_filters)
                    .options(selectinload(Entity.aliases))
                    .order_by(Entity.id)
                    .limit(query.limit + 1)
                )
            )
            .unique()
            .all()
        )
        page, cursor = next_cursor(rows, query.limit, Entity.id, fingerprint)
        return EntityListResponse(
            items=[entity_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    @staticmethod
    def _new(payload: EntityCreateRequest, context: GenericActor) -> Entity:
        entity = Entity(
            user_id=context.user_id,
            **touch_values(context),
            kind=payload.entity_type.value,
            name=payload.name,
            description=missing_to_none(payload.description),
            short_description=missing_to_none(payload.short_description),
            wikidata_id=missing_to_none(payload.wikidata_id),
            nlcr_authority_id=missing_to_none(payload.nlcr_authority_id),
        )
        entity.aliases = [
            Alias(name=value) for value in missing_to_none(payload.aliases) or []
        ]
        return entity

    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        return (await self.create_batch([payload], context))[0]

    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        if not payloads:
            return []
        await ensure_ids(self._session, User, [context.user_id], "actor user")
        entities = [self._new(payload, context) for payload in payloads]
        self._session.add_all(entities)
        await commit(self._session, "entity create violates a persistence constraint")
        return [entity_response(entity) for entity in entities]

    @staticmethod
    def _apply(entity: Entity, payload: EntityPatchRequest) -> bool:
        changed = False
        for name in ("name", "description", "short_description", "wikidata_id", "nlcr_authority_id"):
            value = getattr(payload, name)
            if not is_missing(value) and getattr(entity, name) != value:
                setattr(entity, name, value)
                changed = True
        if not is_missing(payload.aliases):
            existing = {alias.name: alias for alias in entity.aliases}
            if set(existing) != set(payload.aliases):
                entity.aliases = [existing[name] if name in existing else Alias(name=name) for name in payload.aliases]
                changed = True
        return changed

    async def patch(
        self,
        entity_id: uuid.UUID,
        payload: EntityPatchRequest,
        context: GenericActor,
    ) -> EntityResponse | None:
        command = EntityPatchBatchItem(entity_id=entity_id, **payload.model_dump())
        return (await self.patch_batch([command], context))[0]

    async def patch_batch(
        self,
        commands: Sequence[EntityPatchBatchItem],
        context: GenericActor,
    ) -> list[EntityResponse | None]:
        ids = [command.entity_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("entity patch batch requires unique object IDs")
        if not commands:
            return []
        await ensure_ids(self._session, User, [context.user_id], "actor user")
        entities = await self._load_many(ids, lock=True)
        for command in commands:
            entity = entities.get(command.entity_id)
            if entity is not None:
                if self._apply(entity, command):
                    for name, value in touch_values(context).items():
                        setattr(entity, name, value)
        await commit(self._session, "entity patch violates a persistence constraint")
        return [
            entity_response(entity) if (entity := entities.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, entity_id: uuid.UUID) -> bool:
        result = await self.delete_batch([entity_id])
        return result.deleted_count == 1

    async def merge_batch(
        self,
        target_entity_id: uuid.UUID,
        source_entity_ids: Sequence[uuid.UUID],
        target_patch: EntityMergeTargetPatch | None = None,
        *, context: GenericActor,
    ) -> EntityMergeBatchResponse | None:
        if not source_entity_ids:
            raise ValueError("source_entity_ids must not be empty")
        if len(source_entity_ids) != len(set(source_entity_ids)):
            raise ValueError("source_entity_ids must be unique")
        if target_entity_id in source_entity_ids:
            raise ValueError("source and target entity must differ")

        try:
            # A stable lock order avoids deadlocks between simultaneous merges.
            entities = {
                entity.id: entity
                for entity in (
                    await self._session.scalars(
                        select(Entity)
                        .where(Entity.id.in_([target_entity_id, *source_entity_ids]))
                        .order_by(Entity.id)
                        .with_for_update()
                        .options(selectinload(Entity.aliases))
                    )
                ).all()
            }
            if len(entities) != len(source_entity_ids) + 1:
                await self._session.rollback()
                return None

            target = entities[target_entity_id]
            for name, value in touch_values(context).items():
                setattr(target, name, value)
            if target_patch is not None:
                if not is_missing(target_patch.description):
                    target.description = target_patch.description
                if not is_missing(target_patch.short_description):
                    target.short_description = target_patch.short_description
            target_alias_names = {alias.name for alias in target.aliases}
            for source_id in source_entity_ids:
                for alias in entities[source_id].aliases:
                    if alias.name not in target_alias_names:
                        target.aliases.append(Alias(name=alias.name))
                        target_alias_names.add(alias.name)

            face_result = type_cast(
                CursorResult[Any],
                await self._session.execute(
                    update(ImageOccurrence)
                    .where(
                        ImageOccurrence.entity_id.in_(source_entity_ids),
                        ImageOccurrence.occurrence_type == "face",
                    )
                    .values(entity_id=target_entity_id)
                ),
            )
            mention_result = type_cast(
                CursorResult[Any],
                await self._session.execute(
                    update(TextMention)
                    .where(TextMention.entity_id.in_(source_entity_ids))
                    .values(entity_id=target_entity_id)
                ),
            )
            await self._session.execute(
                delete(Entity).where(Entity.id.in_(source_entity_ids))
            )
            response = EntityMergeBatchResponse(
                source_entity_ids=list(source_entity_ids),
                target_entity_id=target_entity_id,
                faces_reassigned=int(face_result.rowcount or 0),
                text_mentions_reassigned=int(mention_result.rowcount or 0),
                merged_entity=entity_response(entities[target_entity_id]),
            )
            await commit(self._session, "entity merge failed")
        except Exception:
            await self._session.rollback()
            raise

        return response

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID]
    ) -> EntityDeleteManyResponse:
        unique = list(dict.fromkeys(entity_ids))
        if not unique:
            return EntityDeleteManyResponse(deleted_count=0)
        await self._session.execute(
            update(ImageOccurrence)
            .where(ImageOccurrence.entity_id.in_(unique))
            .values(entity_id=None)
        )
        await self._session.execute(
            update(TextMention)
            .where(TextMention.entity_id.in_(unique))
            .values(entity_id=None)
        )
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Entity).where(Entity.id.in_(unique))),
        )
        await commit(self._session, "entity delete failed")
        return EntityDeleteManyResponse(deleted_count=int(result.rowcount or 0))

    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        filters = entity_filters(selector.filter)
        ids = list(
            await self._session.scalars(
                select(Entity.id)
                .where(*filters)
                .order_by(Entity.id)
                .limit(selector.limit)
            )
        )
        return await self.delete_batch(ids)

    async def _text_scores(
        self, query: SearchEntitiesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        terms = missing_to_none(query.query.text)
        if terms is None:
            return {}
        collected: dict[uuid.UUID, list[float]] = {}
        for term in terms:
            normalized_term = func.lower(func.unaccent(term))
            candidate_ids = entity_text_candidates(
                normalized_term,
                filters,
            )
            score = func.greatest(
                func.word_similarity(
                    normalized_term,
                    func.coalesce(Entity.name_normalized, ""),
                ),
                func.coalesce(
                    func.max(
                        func.word_similarity(normalized_term, Alias.name_normalized)
                    ),
                    0.0,
                ),
            )
            rows = await self._session.execute(
                select(Entity.id, score.label("score"))
                .outerjoin(Alias, Alias.entity_id == Entity.id)
                .where(*filters, Entity.id.in_(candidate_ids))
                .group_by(Entity.id)
            )
            for item_id, raw_score in rows.all():
                value = float(raw_score)
                if value > 0:
                    collected.setdefault(item_id, []).append(value)
        return aggregate_scores(collected, query.query.score_aggregation)

    async def _face_scores(
        self, query: SearchEntitiesRequest, filters: Sequence[ColumnElement[bool]]
    ) -> dict[uuid.UUID, float]:
        face_ids = missing_to_none(query.query.face_id)
        if face_ids is None:
            return {}
        return await search_face_scores(
            session=self._session,
            target=Entity,
            face_ids=face_ids,
            model_stub=query.query.face_embedding_model,
            filters=filters,
            exclude_reference_faces=query.query.exclude_reference_face_id,
            aggregation=query.query.score_aggregation,
        )

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        filters = entity_filters(query.filter_)
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
        entities = await self._load_many([item[0] for item in page])
        items = [
            FoundEntity(
                **entity_response(entities[item_id]).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchEntitiesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=len(ranked) if query.return_total_count else None,
            cursor=cursor,
        )
