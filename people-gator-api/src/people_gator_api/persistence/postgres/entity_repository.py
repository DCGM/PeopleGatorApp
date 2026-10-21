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
from sqlalchemy.orm.attributes import set_committed_value

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
    Face,
    Entity,
    ImageOccurrence,
    TextMention,
    User,
)
from people_gator_api.persistence.postgres.utils import (
    cursor_fingerprint,
    search_page,
    entity_text_candidates,
    entity_filters,
    entity_response,
    load_link_stats,
    aggregate_scores,
    ensure_ids,
    commit,
    search_face_scores,
    fuse_scores,
)

from people_gator_api.schemas.faces import FaceListFilter
from .utils import face_filters
from people_gator_api.schemas.sorting import RELEVANCE, SortDirection
from .sorting import (
    Builders,
    SortKey,
    SortSpec,
    after_predicate,
    build_spec,
    decode_keyset,
    keyset_page,
    order_by,
    sort_columns,
    sort_ranked,
    text_keys,
)
from .touch import creation_values, touch_values, touch_sources, lock_annotation_graph
from .search_resolution import resolve_entity_search


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
        rows = await self._session.scalars(statement.execution_options(populate_existing=True))
        result = {row.id: row for row in rows.unique().all()}
        await load_link_stats(self._session, result.values(), entities=True)
        return result

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        entity = (await self._load_many([entity_id])).get(entity_id)
        return entity_response(entity) if entity is not None else None

    @staticmethod
    def _sort_spec(field: str | None, direction: SortDirection) -> SortSpec:
        builders: Builders = {
            "name": lambda desc: text_keys(Entity.name_normalized, Entity.name, desc),
            "last_touched_at": lambda desc: [SortKey(Entity.last_touched_at, "datetime", desc)],
            "created_at": lambda desc: [SortKey(Entity.created_at, "datetime", desc)],
        }
        return build_spec(field, direction, Entity.id, builders, "entity_id")

    async def list(self, query: EntityListRequest) -> EntityListResponse:
        filters = entity_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        spec = self._sort_spec(*query.effective_sort())
        after = decode_keyset(query.cursor, spec, fingerprint)
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
        if after is not None:
            page_filters.append(after_predicate(spec, after))
        result = await self._session.execute(
            select(Entity, *sort_columns(spec))
            .where(*page_filters)
            .options(selectinload(Entity.aliases))
            .order_by(*order_by(spec))
            .limit(query.limit + 1)
            .execution_options(populate_existing=True)
        )
        rows = [(row[0], tuple(row[1:])) for row in result.all()]
        page, cursor = keyset_page(rows, query.limit, spec, fingerprint)
        await load_link_stats(self._session, page, entities=True)
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
            **creation_values(context),
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
        # Selection and evidence transitions share the same outer lock. Validate
        # the entire batch before changing anything, including unrelated fields.
        if any(not is_missing(c.thumbnail_face_id) for c in commands):
            await lock_annotation_graph(self._session)
        try:
            await ensure_ids(self._session, User, [context.user_id], "actor user")
            entities = await self._load_many(ids, lock=True)
            selections: dict[uuid.UUID, tuple[uuid.UUID | None, str]] = {}
            requested = [c.thumbnail_face_id for c in commands
                         if not is_missing(c.thumbnail_face_id) and c.thumbnail_face_id is not None]
            owners = dict((await self._session.execute(
                select(Face.id, Face.entity_id).where(Face.id.in_(requested))
            )).all()) if requested else {}
            for command in commands:
                entity = entities.get(command.entity_id)
                if entity is None or is_missing(command.thumbnail_face_id):
                    continue
                if entity.kind != "person":
                    raise ValueError("thumbnail selection is supported only for people")
                face_id = command.thumbnail_face_id
                if face_id is not None:
                    if owners.get(face_id) != entity.id:
                        raise ValueError("thumbnail must be an existing face linked to this person")
                    selections[entity.id] = (face_id, "manual")
                elif entity.thumbnail_mode == "manual":
                    # The database owns automatic resolution. Reload all saved
                    # references together after flushing the trigger's results.
                    selections[entity.id] = (None, "automatic")
            for command in commands:
                entity = entities.get(command.entity_id)
                if entity is None:
                    continue
                changed = self._apply(entity, command)
                selection = selections.get(entity.id)
                if selection is not None and selection != (entity.thumbnail_face_id, entity.thumbnail_mode):
                    entity.thumbnail_face_id, entity.thumbnail_mode = selection
                    changed = True
                if changed:
                    for name, value in touch_values(context).items():
                        setattr(entity, name, value)
            if selections:
                await self._session.flush()
                rows = await self._session.execute(
                    select(Entity.id, Entity.thumbnail_face_id, Entity.thumbnail_mode)
                    .where(Entity.id.in_(selections))
                )
                # Trigger-written values must also be current in the ORM without
                # marking them dirty or issuing one refresh per entity.
                for entity_id, face_id, mode in rows:
                    set_committed_value(entities[entity_id], "thumbnail_face_id", face_id)
                    set_committed_value(entities[entity_id], "thumbnail_mode", mode)
            await commit(self._session, "entity patch violates a persistence constraint")
        except Exception:
            await self._session.rollback()
            raise
        return [
            entity_response(entity) if (entity := entities.get(item_id)) else None
            for item_id in ids
        ]

    async def delete(self, entity_id: uuid.UUID, *, context: GenericActor) -> bool:
        result = await self.delete_batch([entity_id], context=context)
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

        await lock_annotation_graph(self._session)
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
                        # Locked rows must reflect committed portrait state, not
                        # objects cached earlier in this session.
                        .execution_options(populate_existing=True)
                    )
                ).all()
            }
            if len(entities) != len(source_entity_ids) + 1:
                await self._session.rollback()
                return None

            affected_sources = await self._annotation_sources(source_entity_ids)
            target = entities[target_entity_id]
            had_thumbnail = target.thumbnail_face_id is not None
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
                    .values(**touch_values(context), entity_id=target_entity_id, entity_link_state="manual", entity_link_verified_by_user_id=None, entity_link_verified_at=None)
                ),
            )
            mention_result = type_cast(
                CursorResult[Any],
                await self._session.execute(
                    update(TextMention)
                    .where(TextMention.entity_id.in_(source_entity_ids))
                    .values(**touch_values(context), entity_id=target_entity_id, entity_link_state="manual", entity_link_verified_by_user_id=None, entity_link_verified_at=None)
                ),
            )
            await self._session.execute(
                delete(Entity).where(Entity.id.in_(source_entity_ids))
            )
            await self._session.flush()
            if not had_thumbnail and target.kind == "person":
                # Resolve once over the complete merged set, independent of the
                # UPDATE plan's row order. Existing valid target choices survive.
                await self._session.execute(update(Entity).where(Entity.id == target_entity_id)
                    .values(thumbnail_face_id=None, thumbnail_mode="automatic"))
            await self._session.refresh(target, ["thumbnail_face_id", "thumbnail_mode"])
            await touch_sources(self._session, affected_sources, context)
            await load_link_stats(self._session, [target], entities=True)
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

    async def _annotation_sources(self, entity_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        sources: set[uuid.UUID] = set()
        for evidence in (ImageOccurrence, TextMention):
            sources.update(await self._session.scalars(select(evidence.source_id).where(evidence.entity_id.in_(entity_ids))))
        return sources

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID], *, context: GenericActor
    ) -> EntityDeleteManyResponse:
        unique = list(dict.fromkeys(entity_ids))
        if not unique:
            return EntityDeleteManyResponse(deleted_count=0)
        await lock_annotation_graph(self._session)
        affected_sources = await self._annotation_sources(unique)
        await self._session.execute(
            update(ImageOccurrence)
            .where(ImageOccurrence.entity_id.in_(unique))
            .values(**touch_values(context), entity_id=None, entity_link_state=None, entity_link_verified_by_user_id=None, entity_link_verified_at=None)
        )
        await self._session.execute(
            update(TextMention)
            .where(TextMention.entity_id.in_(unique))
            .values(**touch_values(context), entity_id=None, entity_link_state=None, entity_link_verified_by_user_id=None, entity_link_verified_at=None)
        )
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(Entity).where(Entity.id.in_(unique))),
        )
        await touch_sources(self._session, affected_sources, context)
        await commit(self._session, "entity delete failed")
        return EntityDeleteManyResponse(deleted_count=int(result.rowcount or 0))

    async def delete_many(
        self, selector: EntityDeleteManyRequest, *, context: GenericActor
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
        return await self.delete_batch(ids, context=context)

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

    @staticmethod
    def _matching_face_filters(query):
        values = missing_to_none(query.filter_)
        if values is None:
            return []
        fields = {name: getattr(values, name) for name in FaceListFilter.model_fields
                  if name != "entity_id" and hasattr(values, name)}
        return face_filters(FaceListFilter.model_validate(fields))

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
            filters=[*filters, *self._matching_face_filters(query)],
            exclude_reference_faces=query.query.exclude_reference_face_id,
            aggregation=query.query.score_aggregation,
        )

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        fingerprint = cursor_fingerprint(query)
        query = await resolve_entity_search(self._session, query)
        filters = entity_filters(query.filter_)
        if query.query.entity_id is not None and query.query.exclude_reference_face_id:
            filters.append(Entity.id != query.query.entity_id)
        ranked = fuse_scores(
            await self._text_scores(query, filters),
            await self._face_scores(query, filters),
        )
        field, direction = query.effective_sort()
        spec = None if field == RELEVANCE else self._sort_spec(field, direction)
        values: dict[uuid.UUID, tuple[object, ...]] = {}
        if spec is not None and ranked:
            rows = await self._session.execute(
                select(Entity.id, *sort_columns(spec)).where(Entity.id.in_([item[0] for item in ranked]))
            )
            values = {row[0]: tuple(row[1:]) for row in rows.all()}
        ranked = sort_ranked(ranked, spec, direction, values)
        page, cursor = search_page(
            ranked,
            query.cursor,
            query.limit,
            fingerprint,
        )
        entities = await self._load_many([item[0] for item in page])
        witnesses: dict[uuid.UUID, list[uuid.UUID]] = {}
        if not is_missing(query.query.face_id) and entities:
            scores = await search_face_scores(
                session=self._session, target=Face, face_ids=query.query.face_id,
                model_stub=query.query.face_embedding_model,
                filters=[Face.entity_id.in_(entities), *self._matching_face_filters(query)],
                exclude_reference_faces=query.query.exclude_reference_face_id,
                aggregation=query.query.score_aggregation,
            )
            owners = dict((await self._session.execute(select(Face.id, Face.entity_id).select_from(Face).where(Face.id.in_(scores)))).all())
            for detection_id in sorted(scores, key=lambda key: (-scores[key], key.int)):
                witnesses.setdefault(owners[detection_id], []).append(detection_id)
        items = [
            FoundEntity(
                **entity_response(entities[item_id]).model_dump(),
                score=score,
                text_score=text_score,
                face_score=face_score,
                matched_detection_ids=witnesses.get(item_id, [])[:8],
            )
            for item_id, score, text_score, face_score in page
        ]
        return SearchEntitiesResultListResponse(
            items=items,
            limit=query.limit,
            total_count=len(ranked) if query.return_total_count else None,
            cursor=cursor,
        )
