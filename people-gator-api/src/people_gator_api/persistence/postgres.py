"""SQLAlchemy implementation of the backend-neutral persistence contracts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import cast

from pydantic import AnyUrl
from sqlalchemy import ColumnElement, delete, exists, func, or_, select, true
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute, selectinload, with_polymorphic

from people_gator_api.schemas.entities import (
    BoundingBox,
    EntityCreateRequest,
    EntityDeleteManyRequest,
    EntityDeleteManyResponse,
    EntityEmbeddingUpdateRequest,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
    FaceCreateRequest,
    FaceEmbeddingUpdateRequest,
    FaceKeypoint,
    FaceListResponse,
    FaceResponse,
)
from people_gator_api.schemas.enums import (
    AssignmentType,
    EntityType,
    SourceKind,
)
from people_gator_api.schemas.search import (
    FoundDocument,
    SearchDocumentsResultListResponse,
    SearchFacesRequest,
    FoundFace,
    SearchFacesResultListResponse,
    FoundPage,
    SearchPagesResultListResponse,
    SearchDocumentsQuery,
    SearchEntitiesRequest,
    FoundEntity,
    SearchEntitiesResultListResponse,
    SearchPagesQuery,
)
from people_gator_api.schemas.sources import (
    DocumentSourceMetadata,
    PageSourceMetadata,
    SourceRecord,
    SourceRecordListResponse,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListResponse,
    TextMentionResponse,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.crud_services.source_service import (
    SourceCreateSpec,
    source_content,
    stable_source_uuid,
)
from people_gator_api.persistence.contracts import (
    Database,
    EntityListQuery,
    EntityPatchCommand,
    EntityRepository,
    FaceListQuery,
    FacePatchCommand,
    FaceRepository,
    SourceListQuery,
    SourceLookup,
    SourceRepository,
    TextMentionListQuery,
    TextMentionPatchCommand,
    TextMentionRepository,
    UserListQuery,
    UserPatchCommand,
    UserRepository,
    GenericActor,
)
from people_gator_api.services.postgres_demo.models import (
    Alias,
    Document,
    Entity,
    EntityEmbedding,
    Face,
    Image,
    ImageOccurrence,
    ImageOccurrenceEmbedding,
    Page,
    Source,
    TextMention,
    User,
)


def _page_after(
    column: InstrumentedAttribute[uuid.UUID], after_id: uuid.UUID | None
) -> ColumnElement[bool]:
    return column > after_id if after_id is not None else true()


def _entity_response(entity: Entity) -> EntityResponse:
    return EntityResponse(
        entity_id=entity.id,
        user_id=entity.user_id,
        entity_type=EntityType(entity.kind) if entity.kind is not None else None,
        name=entity.name,
        description=entity.description,
        short_description=entity.short_description,
        aliases=[alias.name for alias in entity.aliases],
        wikidata_id=entity.wikidata_id,
        nlcr_authority_id=entity.nlcr_authority_id,
    )


def _source_record(source: Source) -> SourceRecord:
    metadata = None
    if isinstance(source, Page):
        metadata = PageSourceMetadata(
            library=source.library,
            document=source.document_id,
            page=source.page_id,
            kramerius_url=AnyUrl(source.url),
        )
    elif isinstance(source, Document):
        metadata = DocumentSourceMetadata(
            library=source.library, document=source.document_id
        )
    return SourceRecord(
        source_id=source.id,
        source_type=SourceKind(source.source_type),
        uri=source.url,
        metadata=metadata,
    )


def _face_response(face: Face) -> FaceResponse:
    box = face.roi
    return FaceResponse(
        detection_id=face.id,
        identifier=face.identifier,
        source_id=face.source_id,
        entity_id=face.entity_id,
        user_id=face.user_id,
        confidence=face.confidence,
        bounding_box=BoundingBox(
            x=int(box["x"]),
            y=int(box["y"]),
            width=int(box["width"]),
            height=int(box["height"]),
        ),
        keypoints=[
            FaceKeypoint(type=kind, x=point[0], y=point[1])
            for kind, point in zip(face.keypoint_types, face.keypoints)
        ],
    )


def _mention_response(mention: TextMention) -> TextMentionResponse:
    if mention.entity_id is None:
        raise ValueError("The current API cannot represent an unresolved text mention")
    return TextMentionResponse(
        mention_id=mention.id,
        name=mention.mention,
        context=mention.context,
        entity_id=mention.entity_id,
        source_id=mention.source_id,
    )


def _user_response(user: User) -> UserResponse:
    return UserResponse(
        user_id=user.id,
        display_name=user.display_name,
        is_active=user.is_active,
        external_subject=user.external_subject,
        external_issuer=user.external_issuer,
        email=user.email,
    )


class PostgresEntityRepository(EntityRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Entity]:
        if not ids:
            return {}
        rows = await self._session.scalars(
            select(Entity)
            .where(Entity.id.in_(ids))
            .options(selectinload(Entity.aliases))
        )
        return {row.id: row for row in rows.unique().all()}

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        rows = await self._load_many([entity_id])
        entity = rows.get(entity_id)
        return _entity_response(entity) if entity is not None else None

    def _filters(self, query: EntityListQuery) -> list[ColumnElement[bool]]:
        filters = [_page_after(Entity.id, query.after_id)]
        if query.entity_type is not None:
            filters.append(Entity.kind == query.entity_type.value)
        if query.wikidata_id is not None:
            filters.append(Entity.wikidata_id == query.wikidata_id)
        if query.nlcr_authority_id is not None:
            filters.append(Entity.nlcr_authority_id == query.nlcr_authority_id)
        if query.owner_user_id is not None:
            filters.append(Entity.user_id == query.owner_user_id)
        if query.source_id is not None:
            filters.append(
                or_(
                    exists().where(
                        ImageOccurrence.entity_id == Entity.id,
                        ImageOccurrence.source_id == query.source_id,
                    ),
                    exists().where(
                        TextMention.entity_id == Entity.id,
                        TextMention.source_id == query.source_id,
                    ),
                )
            )
        if query.assignment == AssignmentType.face:
            filters.append(exists().where(ImageOccurrence.entity_id == Entity.id))
        elif query.assignment == AssignmentType.text_mention:
            filters.append(exists().where(TextMention.entity_id == Entity.id))
        return filters

    async def list(self, query: EntityListQuery) -> EntityListResponse:
        filters = self._filters(query)
        total = await self._session.scalar(
            select(func.count()).select_from(Entity).where(*filters)
        )
        rows = await self._session.scalars(
            select(Entity)
            .where(*filters)
            .options(selectinload(Entity.aliases))
            .order_by(Entity.id)
            .limit(query.limit)
        )
        items = [_entity_response(row) for row in rows.unique().all()]
        return EntityListResponse(
            items=items,
            total_count=total or 0,
            limit=query.limit,
            cursor=items[-1].entity_id
            if len(items) == query.limit and items
            else None,
        )

    def _new(self, payload: EntityCreateRequest, user_id: uuid.UUID) -> Entity:
        entity = Entity(
            user_id=user_id,
            kind=payload.entity_type.value if payload.entity_type is not None else None,
            name=payload.name,
            description=payload.description,
            short_description=payload.short_description,
            wikidata_id=payload.wikidata_id,
            nlcr_authority_id=payload.nlcr_authority_id,
            aliases=[Alias(name=name) for name in payload.aliases or []],
        )
        seen_embeddings: set[tuple[str, str]] = set()
        for embedding in payload.embeddings:
            key = (embedding.field, embedding.model_identifier)
            if key in seen_embeddings:
                raise ValueError(
                    f"duplicate entity embedding field/model pair: {embedding.field}/{embedding.model_identifier}"
                )
            seen_embeddings.add(key)
            entity.embeddings.append(
                EntityEmbedding(
                    field=embedding.field,
                    model=embedding.model_identifier,
                    dimensions=len(embedding.vector),
                    embedding=embedding.vector,
                )
            )
        return entity

    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        entity = self._new(payload, context.user_id)
        self._session.add(entity)
        await self._session.commit()
        return _entity_response(entity)

    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        entities = [self._new(payload, context.user_id) for payload in payloads]
        self._session.add_all(entities)
        await self._session.commit()
        return [_entity_response(entity) for entity in entities]

    @staticmethod
    def _apply(entity: Entity, payload: EntityPatchRequest) -> None:
        updates = payload.model_dump(exclude_unset=True)
        has_aliases = "aliases" in updates
        aliases = cast(list[str] | None, updates.pop("aliases", None))
        for name, value in updates.items():
            setattr(entity, name, value)
        if has_aliases:
            entity.aliases = [Alias(name=name) for name in aliases or []]

    async def patch(
        self, entity_id: uuid.UUID, payload: EntityPatchRequest
    ) -> EntityResponse | None:
        entity = (await self._load_many([entity_id])).get(entity_id)
        if entity is None:
            return None
        self._apply(entity, payload)
        await self._session.commit()
        return _entity_response(entity)

    async def patch_batch(
        self, commands: Sequence[EntityPatchCommand]
    ) -> list[EntityResponse | None]:
        ids = [command.entity_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("entity patch batch requires unique object IDs")
        entities = await self._load_many(ids)
        for command in commands:
            if entity := entities.get(command.entity_id):
                self._apply(entity, command.patch)
        await self._session.commit()
        return [
            _entity_response(entity) if (entity := entities.get(item)) else None
            for item in ids
        ]

    async def update_embeddings_batch(
        self, payloads: Sequence[EntityEmbeddingUpdateRequest]
    ) -> int:
        if not payloads:
            return 0
        keys: set[tuple[uuid.UUID, str, str]] = set()
        for payload in payloads:
            for embedding in payload.embeddings:
                key = (
                    payload.entity_id,
                    embedding.field,
                    embedding.model_identifier,
                )
                if key in keys:
                    raise ValueError(
                        f"duplicate entity embedding update for {payload.entity_id}/{embedding.field}/{embedding.model_identifier}"
                    )
                keys.add(key)
        entity_ids = {key[0] for key in keys}
        rows = await self._session.scalars(
            select(EntityEmbedding).where(EntityEmbedding.entity_id.in_(entity_ids))
        )
        existing = {(row.entity_id, row.field, row.model): row for row in rows.all()}
        for payload in payloads:
            for value in payload.embeddings:
                key = (payload.entity_id, value.field, value.model_identifier)
                embedding = existing.get(key)
                if embedding is None:
                    self._session.add(
                        EntityEmbedding(
                            entity_id=payload.entity_id,
                            field=value.field,
                            model=value.model_identifier,
                            dimensions=len(value.vector),
                            embedding=value.vector,
                        )
                    )
                else:
                    embedding.dimensions = len(value.vector)
                    embedding.embedding = value.vector
        await self._session.commit()
        return len(keys)

    async def delete(self, entity_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([entity_id]))

    async def delete_batch(self, entity_ids: Sequence[uuid.UUID]) -> int:
        if not entity_ids:
            return 0
        result = await self._session.execute(
            delete(Entity).where(Entity.id.in_(set(entity_ids)))
        )
        await self._session.commit()
        return result.rowcount  # type: ignore[attr-defined]

    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        statement = delete(Entity)
        mode = "all"
        if selector.entity_ids:
            statement = statement.where(Entity.id.in_(set(selector.entity_ids)))
            mode = "entity_ids"
        elif selector.entity_type is not None:
            statement = statement.where(Entity.kind == selector.entity_type.value)
            mode = "entity_type"
        result = await self._session.execute(statement)
        await self._session.commit()
        return EntityDeleteManyResponse(
            mode=mode,
            deleted_count=result.rowcount,  # type: ignore[attr-defined]
        )

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        if not query.q:
            return SearchEntitiesResultListResponse(
                items=[], total_count=0, limit=query.limit, cursor=None
            )
        term = " ".join(query.q).strip()
        score = func.greatest(
            func.similarity(func.coalesce(Entity.name, ""), term),
            func.coalesce(func.max(func.similarity(Alias.name, term)), 0.0),
        )
        statement = (
            select(Entity, score.label("score"))
            .outerjoin(Alias, Alias.entity_id == Entity.id)
            .group_by(Entity.id)
            .having(score > 0.1)
            .order_by(score.desc(), Entity.id)
            .limit(query.limit)
            .options(selectinload(Entity.aliases))
        )
        if query.entity_types:
            types = (
                query.entity_types
                if isinstance(query.entity_types, list)
                else [query.entity_types]
            )
            statement = statement.where(Entity.kind.in_([item.value for item in types]))
        rows = (await self._session.execute(statement)).all()
        items = [
            FoundEntity(
                entity_id=entity.id,
                entity_type=EntityType(entity.kind) if entity.kind else None,
                name=entity.name or "",
                description=entity.description or "",
                short_description=entity.short_description or "",
                aliases=[alias.name for alias in entity.aliases],
                score=float(rank),
            )
            for entity, rank in rows
        ]
        return SearchEntitiesResultListResponse(
            items=items,
            total_count=len(items),
            limit=query.limit,
            cursor=items[-1].entity_id if items else None,
        )


class PostgresSourceRepository(SourceRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session
        self._source = with_polymorphic(Source, [Document, Page, Image])

    async def lookup(self, lookup: SourceLookup) -> SourceRecord | None:
        statement = select(self._source)
        if lookup.source_id is not None:
            statement = statement.where(Source.id == lookup.source_id)
        elif lookup.url is not None and lookup.source_type is None:
            statement = statement.where(Source.url == lookup.url)
        elif lookup.source_type is not None:
            statement = statement.where(Source.source_type == lookup.source_type.value)
            if lookup.source_type == SourceKind.page:
                statement = statement.where(
                    Page.library == lookup.library,
                    Page.document_id == lookup.document_id,
                    Page.page_id == lookup.page_id,
                )
            elif lookup.source_type == SourceKind.document:
                statement = statement.where(
                    Document.library == lookup.library,
                    Document.document_id == lookup.document_id,
                )
            else:
                statement = statement.where(Source.url == lookup.url)
        else:
            raise ValueError("source lookup requires an ID, URL, or typed identity")
        source = await self._session.scalar(statement.limit(1))
        return _source_record(source) if source is not None else None

    async def list(self, query: SourceListQuery) -> SourceRecordListResponse:
        filters: list[ColumnElement[bool]] = [_page_after(Source.id, query.after_id)]
        if query.source_type is not None:
            filters.append(Source.source_type == query.source_type.value)
        if query.url is not None:
            filters.append(Source.url == query.url)
        if query.source_ids is not None:
            filters.append(Source.id.in_(query.source_ids))
        if query.library is not None:
            filters.append(
                or_(Page.library == query.library, Document.library == query.library)
            )
        if query.document_id is not None:
            filters.append(
                or_(
                    Page.document_id == query.document_id,
                    Document.document_id == query.document_id,
                )
            )
        if query.page_id is not None:
            filters.append(Page.page_id == query.page_id)
        total = await self._session.scalar(
            select(func.count()).select_from(self._source).where(*filters)
        )
        rows = await self._session.scalars(
            select(self._source).where(*filters).order_by(Source.id).limit(query.limit)
        )
        items = [_source_record(row) for row in rows.all()]
        return SourceRecordListResponse(
            items=items,
            total_count=total or 0,
            limit=query.limit,
            after_id=items[-1].source_id
            if len(items) == query.limit and items
            else None,
        )

    def _new(self, spec: SourceCreateSpec) -> Source:
        url, _metadata = source_content(
            spec.source_type,
            library=spec.library,
            document_id=spec.document_id,
            page_id=spec.page_id,
            url=spec.url,
        )
        source_id = stable_source_uuid(
            spec.source_type,
            library=spec.library,
            document_id=spec.document_id,
            page_id=spec.page_id,
            url=spec.url,
        )
        if spec.source_type == SourceKind.page:
            return Page(
                id=source_id,
                url=url,
                library=spec.library,
                document_id=spec.document_id,
                page_id=spec.page_id,
            )
        if spec.source_type == SourceKind.document:
            return Document(
                id=source_id,
                url=url,
                library=spec.library,
                document_id=spec.document_id,
            )
        return Image(id=source_id, url=url)

    async def get_or_create(self, spec: SourceCreateSpec) -> tuple[SourceRecord, bool]:
        source = self._new(spec)
        existing = await self._session.get(Source, source.id)
        if existing is not None:
            return _source_record(existing), False
        self._session.add(source)
        await self._session.commit()
        return _source_record(source), True

    async def get_or_create_batch(
        self, specs: Sequence[SourceCreateSpec]
    ) -> list[SourceRecord]:
        candidates = [self._new(spec) for spec in specs]
        ids = [source.id for source in candidates]
        existing = {
            item.id: item
            for item in (
                await self._session.scalars(
                    select(self._source).where(Source.id.in_(set(ids)))
                )
            ).all()
        }
        additions = {item.id: item for item in candidates if item.id not in existing}
        self._session.add_all(additions.values())
        await self._session.commit()
        return [
            _source_record(existing.get(item.id) or additions[item.id])
            for item in candidates
        ]

    async def delete(self, source_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([source_id]))

    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        if not source_ids:
            return 0
        result = await self._session.execute(
            delete(Source).where(Source.id.in_(set(source_ids)))
        )
        await self._session.commit()
        return result.rowcount  # type: ignore[attr-defined]

    async def search_pages(
        self, query: SearchPagesQuery
    ) -> SearchPagesResultListResponse:
        try:
            source_id = uuid.UUID(query.q)
        except ValueError:
            return SearchPagesResultListResponse(
                items=[], total_count=0, limit=query.limit
            )
        page = await self._session.get(Page, source_id)
        items = (
            [
                FoundPage(
                    source_id=page.id,
                    document_id=page.document_id,
                    page_id=page.page_id,
                    matching_score=1.0,
                )
            ]
            if page is not None
            else []
        )
        return SearchPagesResultListResponse(
            items=items, total_count=len(items), limit=query.limit
        )

    async def search_documents(
        self, query: SearchDocumentsQuery
    ) -> SearchDocumentsResultListResponse:
        try:
            source_id = uuid.UUID(query.q)
        except ValueError:
            return SearchDocumentsResultListResponse(
                items=[], total_count=0, limit=query.limit
            )
        document = await self._session.get(Document, source_id)
        items = (
            [
                FoundDocument(
                    source_id=document.id,
                    document_id=document.document_id,
                    score_text=1.0,
                )
            ]
            if document is not None
            else []
        )
        return SearchDocumentsResultListResponse(
            items=items, total_count=len(items), limit=query.limit
        )


class PostgresFaceRepository(FaceRepository):
    def __init__(
        self, session: AsyncSession, sources: PostgresSourceRepository
    ) -> None:
        super().__init__()
        self._session = session
        self._sources = sources

    async def _load_many(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, Face]:
        if not ids:
            return {}
        rows = await self._session.scalars(select(Face).where(Face.id.in_(ids)))
        return {row.id: row for row in rows.all()}

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        face = (await self._load_many([detection_id])).get(detection_id)
        return _face_response(face) if face is not None else None

    async def list(self, query: FaceListQuery) -> FaceListResponse:
        filters: list[ColumnElement[bool]] = [_page_after(Face.id, query.after_id)]
        if query.source_id is not None:
            filters.append(Face.source_id == query.source_id)
        if query.entity_id is not None:
            filters.append(Face.entity_id == query.entity_id)
        if query.owner_user_id is not None:
            filters.append(Face.user_id == query.owner_user_id)
        total = await self._session.scalar(
            select(func.count()).select_from(Face).where(*filters)
        )
        rows = await self._session.scalars(
            select(Face).where(*filters).order_by(Face.id).limit(query.limit)
        )
        items = [_face_response(row) for row in rows.all()]
        return FaceListResponse(
            items=items,
            total_count=total or 0,
            limit=query.limit,
            after_id=items[-1].detection_id
            if len(items) == query.limit and items
            else None,
        )

    async def _source_id(self, payload: FaceCreateRequest) -> uuid.UUID:
        if payload.source_id is not None:
            if await self._session.get(Source, payload.source_id) is None:
                raise ValueError("Face source does not exist")
            return payload.source_id
        assert payload.source is not None
        descriptor = payload.source
        if descriptor.page is not None:
            spec = SourceCreateSpec(
                source_type=SourceKind.page,
                library=descriptor.page.library,
                document_id=descriptor.page.document_id,
                page_id=descriptor.page.page_id,
            )
        elif descriptor.document is not None:
            spec = SourceCreateSpec(
                source_type=SourceKind.document,
                library=descriptor.document.library,
                document_id=descriptor.document.document_id,
            )
        else:
            assert descriptor.image is not None
            spec = SourceCreateSpec(
                source_type=SourceKind.image, url=str(descriptor.image.url)
            )
        return (await self._sources.get_or_create(spec))[0].source_id

    async def _new(self, payload: FaceCreateRequest, context: GenericActor) -> Face:
        if len(payload.keypoints) != 5:
            raise ValueError("Face requires exactly five keypoints")
        face = Face(
            source_id=await self._source_id(payload),
            entity_id=payload.entity_id,
            user_id=context.user_id,
            identifier=payload.identifier,
            confidence=payload.confidence,
            roi=payload.bounding_box.model_dump(),
            keypoints=[[item.x, item.y] for item in payload.keypoints],
            keypoint_types=[item.type for item in payload.keypoints],
        )
        seen_models: set[str] = set()
        for embedding in payload.embeddings:
            if embedding.model_identifier in seen_models:
                raise ValueError(
                    f"duplicate face embedding model: {embedding.model_identifier}"
                )
            seen_models.add(embedding.model_identifier)
            face.embeddings.append(
                ImageOccurrenceEmbedding(
                    model=embedding.model_identifier,
                    dimensions=len(embedding.vector),
                    embedding=embedding.vector,
                )
            )
        return face

    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        face = await self._new(payload, context)
        self._session.add(face)
        await self._session.commit()
        return _face_response(face)

    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        faces = [await self._new(payload, context) for payload in payloads]
        self._session.add_all(faces)
        await self._session.commit()
        return [_face_response(face) for face in faces]

    async def patch(
        self, detection_id: uuid.UUID, entity_id: uuid.UUID | None
    ) -> FaceResponse | None:
        face = (await self._load_many([detection_id])).get(detection_id)
        if face is None:
            return None
        face.entity_id = entity_id
        await self._session.commit()
        return _face_response(face)

    async def patch_batch(
        self, commands: Sequence[FacePatchCommand]
    ) -> list[FaceResponse | None]:
        ids = [command.detection_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("face patch batch requires unique object IDs")
        faces = await self._load_many(ids)
        for command in commands:
            if face := faces.get(command.detection_id):
                face.entity_id = command.entity_id
        await self._session.commit()
        return [
            _face_response(face) if (face := faces.get(item)) else None for item in ids
        ]

    async def update_embeddings_batch(
        self, payloads: Sequence[FaceEmbeddingUpdateRequest]
    ) -> int:
        if not payloads:
            return 0
        ids = [payload.detection_id for payload in payloads]
        rows = await self._session.scalars(
            select(ImageOccurrenceEmbedding).where(
                ImageOccurrenceEmbedding.occurrence_id.in_(ids)
            )
        )
        by_key = {(row.occurrence_id, row.model): row for row in rows.all()}
        updated_count = 0
        seen_keys: set[tuple[uuid.UUID, str]] = set()
        for payload in payloads:
            for value in payload.embeddings:
                key = (payload.detection_id, value.model_identifier)
                if key in seen_keys:
                    raise ValueError(
                        f"duplicate face embedding update for {payload.detection_id}/{value.model_identifier}"
                    )
                seen_keys.add(key)
                embedding = by_key.get(key)
                if embedding is None:
                    embedding = ImageOccurrenceEmbedding(
                        occurrence_id=payload.detection_id,
                        model=value.model_identifier,
                        dimensions=len(value.vector),
                        embedding=value.vector,
                    )
                    self._session.add(embedding)
                else:
                    embedding.dimensions = len(value.vector)
                    embedding.embedding = value.vector
                updated_count += 1
        await self._session.commit()
        return updated_count

    async def delete(self, detection_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([detection_id]))

    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int:
        if not detection_ids:
            return 0
        result = await self._session.execute(
            delete(ImageOccurrence).where(ImageOccurrence.id.in_(set(detection_ids)))
        )
        await self._session.commit()
        return result.rowcount  # type: ignore[attr-defined]

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        if not query.q_face_id:
            return SearchFacesResultListResponse(
                items=[], total_count=0, limit=query.limit
            )
        references = await self._session.scalars(
            select(ImageOccurrenceEmbedding).where(
                ImageOccurrenceEmbedding.occurrence_id.in_(query.q_face_id),
                ImageOccurrenceEmbedding.model == query.embedding_model.value,
            )
        )
        reference_vectors = [row.embedding for row in references.all()]
        if not reference_vectors:
            return SearchFacesResultListResponse(
                items=[], total_count=0, limit=query.limit
            )
        candidates: dict[uuid.UUID, tuple[Face, float]] = {}
        for vector in reference_vectors:
            distance = ImageOccurrenceEmbedding.embedding.cosine_distance(vector)
            rows = (
                await self._session.execute(
                    select(Face, distance.label("distance"))
                    .join(
                        ImageOccurrenceEmbedding,
                        ImageOccurrenceEmbedding.occurrence_id == Face.id,
                    )
                    .where(
                        ImageOccurrenceEmbedding.model == query.embedding_model.value,
                        Face.id.not_in(query.q_face_id),
                    )
                    .order_by(distance)
                    .limit(query.limit)
                )
            ).all()
            for face, raw_distance in rows:
                similarity = 1.0 - float(raw_distance)
                current = candidates.get(face.id)
                if current is None or similarity > current[1]:
                    candidates[face.id] = (face, similarity)
        ranked = sorted(candidates.values(), key=lambda item: -item[1])[: query.limit]
        items = [
            FoundFace(
                face_id=face.id,
                source_id=face.source_id,
                entity_id=face.entity_id,
                bounding_box=_face_response(face).bounding_box,
                matching_score=score,
            )
            for face, score in ranked
        ]
        return SearchFacesResultListResponse(
            items=items, total_count=len(items), limit=query.limit
        )


class PostgresTextMentionRepository(TextMentionRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(
        self, ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, TextMention]:
        if not ids:
            return {}
        rows = await self._session.scalars(
            select(TextMention).where(TextMention.id.in_(ids))
        )
        return {row.id: row for row in rows.all()}

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        mention = (await self._load_many([mention_id])).get(mention_id)
        return _mention_response(mention) if mention is not None else None

    async def list(self, query: TextMentionListQuery) -> TextMentionListResponse:
        filters: list[ColumnElement[bool]] = [
            _page_after(TextMention.id, query.after_id)
        ]
        if query.source_id is not None:
            filters.append(TextMention.source_id == query.source_id)
        if query.entity_id is not None:
            filters.append(TextMention.entity_id == query.entity_id)
        total = await self._session.scalar(
            select(func.count()).select_from(TextMention).where(*filters)
        )
        rows = await self._session.scalars(
            select(TextMention)
            .where(*filters)
            .order_by(TextMention.id)
            .limit(query.limit)
        )
        items = [_mention_response(row) for row in rows.all()]
        return TextMentionListResponse(
            items=items,
            total_count=total or 0,
            limit=query.limit,
            cursor=items[-1].mention_id
            if len(items) == query.limit and items
            else None,
        )

    @staticmethod
    def _new(payload: TextMentionCreateRequest) -> TextMention:
        return TextMention(
            mention=payload.name,
            context=payload.context,
            entity_id=payload.entity_id,
            source_id=payload.source_id,
        )

    async def create(self, payload: TextMentionCreateRequest) -> TextMentionResponse:
        mention = self._new(payload)
        self._session.add(mention)
        await self._session.commit()
        return _mention_response(mention)

    async def create_batch(
        self, payloads: Sequence[TextMentionCreateRequest]
    ) -> list[TextMentionResponse]:
        mentions = [self._new(payload) for payload in payloads]
        self._session.add_all(mentions)
        await self._session.commit()
        return [_mention_response(mention) for mention in mentions]

    async def patch(
        self, mention_id: uuid.UUID, entity_id: uuid.UUID
    ) -> TextMentionResponse | None:
        mention = (await self._load_many([mention_id])).get(mention_id)
        if mention is None:
            return None
        mention.entity_id = entity_id
        await self._session.commit()
        return _mention_response(mention)

    async def patch_batch(
        self, commands: Sequence[TextMentionPatchCommand]
    ) -> list[TextMentionResponse | None]:
        ids = [command.mention_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("text mention patch batch requires unique object IDs")
        mentions = await self._load_many(ids)
        for command in commands:
            if mention := mentions.get(command.mention_id):
                mention.entity_id = command.entity_id
        await self._session.commit()
        return [
            _mention_response(mention) if (mention := mentions.get(item)) else None
            for item in ids
        ]

    async def delete(self, mention_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([mention_id]))

    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int:
        if not mention_ids:
            return 0
        result = await self._session.execute(
            delete(TextMention).where(TextMention.id.in_(set(mention_ids)))
        )
        await self._session.commit()
        return result.rowcount  # type: ignore[attr-defined]


class PostgresUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def _load_many(self, ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, User]:
        if not ids:
            return {}
        rows = await self._session.scalars(select(User).where(User.id.in_(ids)))
        return {row.id: row for row in rows.all()}

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        user = (await self._load_many([user_id])).get(user_id)
        return _user_response(user) if user is not None else None

    async def list(self, query: UserListQuery) -> UserListResponse:
        filters: list[ColumnElement[bool]] = [_page_after(User.id, query.after_id)]
        if query.is_active is not None:
            filters.append(User.is_active == query.is_active)
        total = await self._session.scalar(
            select(func.count()).select_from(User).where(*filters)
        )
        rows = await self._session.scalars(
            select(User).where(*filters).order_by(User.id).limit(query.limit)
        )
        items = [_user_response(row) for row in rows.all()]
        return UserListResponse(
            items=items,
            total_count=total or 0,
            limit=query.limit,
            cursor=items[-1].user_id if len(items) == query.limit and items else None,
        )

    @staticmethod
    def _new(payload: UserCreateRequest) -> User:
        return User(**payload.model_dump())

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        user = self._new(payload)
        self._session.add(user)
        await self._session.commit()
        return _user_response(user)

    async def import_batch(
        self, payloads: Sequence[UserCreateRequest]
    ) -> list[UserResponse]:
        users = [self._new(payload) for payload in payloads]
        self._session.add_all(users)
        await self._session.commit()
        return [_user_response(user) for user in users]

    @staticmethod
    def _apply(user: User, payload: UserPatchRequest) -> None:
        for name, value in payload.model_dump(exclude_unset=True).items():
            setattr(user, name, value)

    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        user = (await self._load_many([user_id])).get(user_id)
        if user is None:
            return None
        self._apply(user, payload)
        await self._session.commit()
        return _user_response(user)

    async def patch_batch(
        self, commands: Sequence[UserPatchCommand]
    ) -> list[UserResponse | None]:
        ids = [command.user_id for command in commands]
        if len(ids) != len(set(ids)):
            raise ValueError("user patch batch requires unique object IDs")
        users = await self._load_many(ids)
        for command in commands:
            if user := users.get(command.user_id):
                self._apply(user, command.patch)
        await self._session.commit()
        return [
            _user_response(user) if (user := users.get(item)) else None for item in ids
        ]

    async def delete(self, user_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([user_id]))

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        if not user_ids:
            return 0
        result = await self._session.execute(
            delete(User).where(User.id.in_(set(user_ids)))
        )
        await self._session.commit()
        return result.rowcount  # type: ignore[attr-defined]

    async def get_or_create(
        self, *, external_subject: str, external_issuer: str
    ) -> UserResponse:
        user = await self._session.scalar(
            select(User).where(
                User.external_subject == external_subject,
                User.external_issuer == external_issuer,
            )
        )
        if user is None:
            user = User(
                display_name=external_subject,
                is_active=True,
                external_subject=external_subject,
                external_issuer=external_issuer,
            )
            self._session.add(user)
            await self._session.commit()
        return _user_response(user)


def postgres_database(session: AsyncSession) -> Database:
    """Bind all repositories to one request-scoped SQLAlchemy session."""
    sources = PostgresSourceRepository(session)
    return Database(
        entities=PostgresEntityRepository(session),
        sources=sources,
        faces=PostgresFaceRepository(session, sources),
        text_mentions=PostgresTextMentionRepository(session),
        users=PostgresUserRepository(session),
    )
