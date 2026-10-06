"""Self-contained Weaviate implementation of the persistence contracts.

This package owns the Weaviate adapter, client construction, collection schemas,
and backend query helpers. Application lifecycle lives in database_service.
The contract adapter talks to the v4 client directly.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol, overload

from pydantic import BaseModel
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.filters import FilterReturn, FilterValuesList
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties
from weaviate.collections.collection.async_ import CollectionAsync

from people_gator_api.persistence.contracts import (
    CreateResult,
    Database,
    EntityRepository,
    FaceModelRepository,
    FaceRepository,
    SourceRepository,
    TextMentionRepository,
    UserRepository,
)
from people_gator_api.persistence.weaviate.schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    FACE_VECTOR_PREFIX,
    SOURCE_COLLECTION,
    TEXT_MENTION_COLLECTION,
    USER_COLLECTION,
    model_vector_name,
)
from people_gator_api.schemas.common import (
    GenericActor,
    GenericListRequest,
    GenericListResponse,
)
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
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FaceListFilter,
    FaceListRequest,
    FaceListResponse,
    FacePatchBatchItem,
    FacePatchRequest,
    FaceResponse,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListRequest,
    TextMentionListResponse,
    TextMentionPatchBatchItem,
    TextMentionPatchRequest,
    TextMentionResponse,
)
from people_gator_api.schemas.missing import MissingType, is_missing, missing_to_none
from people_gator_api.schemas.search import (
    RRF_K,
    FoundDocument,
    FoundEntity,
    FoundFace,
    FoundItemBase,
    FoundPage,
    SearchDocumentsRequest,
    SearchDocumentsResultListResponse,
    SearchEntitiesRequest,
    SearchEntitiesResultListResponse,
    SearchFacesRequest,
    SearchFacesResultListResponse,
    SearchPagesRequest,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import (
    DocumentResponse,
    GenericSourceCreateRequest,
    GenericSourceListFilter,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    PageResponse,
    document_url,
    page_url,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.utils.uuid_utils import new_uuid6

FACE_MODEL_COLLECTION = "FaceModel"
_SOURCE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "http://peoplegator/source")
_REFS = {
    ENTITY_COLLECTION: ("user",),
    FACE_COLLECTION: ("source", "entity", "user"),
    TEXT_MENTION_COLLECTION: ("source", "entity"),
}


def _refs(*names: str) -> list[QueryReference]:
    return [QueryReference(link_on=n, return_properties=[]) for n in names]


class _StoredObject(Protocol):
    """The common read-only shape of Weaviate list and single-object results."""

    @property
    def uuid(self) -> uuid.UUID: ...

    @property
    def properties(self) -> Mapping[str, object]: ...

    @property
    def references(self) -> CrossReferences | None: ...

    @property
    def vector(self) -> Mapping[str, list[float] | list[list[float]]]: ...


@overload
def _ref(obj: _StoredObject, name: str, required: Literal[True]) -> uuid.UUID: ...


@overload
def _ref(
    obj: _StoredObject, name: str, required: Literal[False] = False
) -> uuid.UUID | None: ...


def _ref(obj: _StoredObject, name: str, required: bool = False) -> uuid.UUID | None:
    value = obj.references.get(name) if obj.references is not None else None
    result = value.objects[0].uuid if value is not None and value.objects else None
    if required and result is None:
        raise ValueError(f"stored object lacks {name} reference")
    return result


def _props(
    model: BaseModel, exclude: set[str] | None = None
) -> dict[str, WeaviateField]:
    """Serialize API fields to the JSON-compatible property types accepted by Weaviate.

    Pydantic omits MISSING fields and converts enums, URLs, and UUIDs to strings.
    Keeping this conversion at the boundary avoids leaking untyped client data.
    """
    return model.model_dump(mode="json", exclude=exclude, exclude_unset=True)


def _parse_user(o: _StoredObject) -> UserResponse:
    return UserResponse.model_validate({**o.properties, "user_id": o.uuid})


def _parse_entity(o: _StoredObject) -> EntityResponse:
    p = dict(o.properties)
    p["aliases"] = p.get("aliases") or None
    return EntityResponse.model_validate(
        {**p, "entity_id": o.uuid, "user_id": _ref(o, "user", True)}
    )


def _parse_source(o: _StoredObject) -> GenericSourceResponse:
    p = o.properties
    return GenericSourceResponse.model_validate(
        {
            "source_id": o.uuid,
            "source_type": p["source_type"],
            "url": p["uri"],
            "library": p.get("library"),
            "document_id": p.get("document"),
            "page_id": p.get("page"),
        }
    )


def _parse_face(o: _StoredObject) -> FaceResponse:
    prefix = model_vector_name(FACE_VECTOR_PREFIX, "x")[:-1]
    return FaceResponse.model_validate(
        {
            **o.properties,
            "detection_id": o.uuid,
            "source_id": _ref(o, "source", True),
            "entity_id": _ref(o, "entity"),
            "user_id": _ref(o, "user", True),
            "embeddings": sorted(
                k[len(prefix) :] for k in o.vector if k.startswith(prefix)
            ),
        }
    )


def _parse_mention(o: _StoredObject) -> TextMentionResponse:
    return TextMentionResponse.model_validate(
        {
            **o.properties,
            "mention_id": o.uuid,
            "source_id": _ref(o, "source", True),
            "entity_id": _ref(o, "entity"),
        }
    )


def _all(fs: Sequence[FilterReturn]) -> FilterReturn | None:
    return None if not fs else fs[0] if len(fs) == 1 else Filter.all_of(list(fs))


def _property(name: str, values: FilterValuesList) -> FilterReturn:
    return Filter.by_property(name).contains_any(values)


def _reference(name: str, values: Sequence[uuid.UUID]) -> FilterReturn:
    fs = [Filter.by_ref(link_on=name).by_id().equal(v) for v in values]
    return fs[0] if len(fs) == 1 else Filter.any_of(fs)


def _direct(
    value: BaseModel | MissingType | None, mapping: Mapping[str, str]
) -> list[FilterReturn]:
    if value is None or is_missing(value):
        return []
    return [
        _property(stored, getattr(value, api))
        for api, stored in mapping.items()
        if not is_missing(getattr(value, api))
    ]


def _fingerprint(q: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            q.model_dump(mode="json", exclude={"cursor"}),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _encode(i: uuid.UUID, f: str) -> str:
    return (
        base64.urlsafe_b64encode(json.dumps({"i": str(i), "f": f}).encode())
        .decode()
        .rstrip("=")
    )


def _decode(c: str | None, f: str) -> uuid.UUID | None:
    if c is None:
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)))
    except Exception as e:
        raise ValueError("malformed cursor") from e
    if d.get("f") != f:
        raise ValueError("cursor was produced by a different query")
    try:
        return uuid.UUID(d["i"])
    except Exception as e:
        raise ValueError("malformed cursor") from e


async def _get(c: WeaviateAsyncClient, n: str, i: uuid.UUID) -> _StoredObject | None:
    return await c.collections.get(n).query.fetch_object_by_id(
        i,
        include_vector=n == FACE_COLLECTION,
        return_references=_refs(*_REFS.get(n, ())),
    )


async def _exists(c: WeaviateAsyncClient, n: str, i: uuid.UUID) -> bool:
    return await c.collections.get(n).data.exists(i)


async def _require(c: WeaviateAsyncClient, n: str, i: uuid.UUID, label: str) -> None:
    if not await _exists(c, n, i):
        raise ValueError(f"{label} {i} does not exist")


async def _page[T: BaseModel, R: BaseModel](
    c: WeaviateAsyncClient,
    n: str,
    q: GenericListRequest,
    fs: Sequence[FilterReturn],
    parse: Callable[[_StoredObject], T],
    response: type[R],
) -> R:
    fp = _fingerprint(q)
    after = _decode(q.cursor, fp)
    collection = c.collections.get(n)
    where = _all(fs)
    count = None
    if q.return_total_count:
        count = int(
            (
                await collection.aggregate.over_all(total_count=True, filters=where)
            ).total_count
            or 0
        )
    if q.limit == 0:
        return response(items=[], limit=0, total_count=count, cursor=None)
    result = await collection.query.fetch_objects(
        filters=where,
        limit=q.limit + 1,
        after=after,
        include_vector=n == FACE_COLLECTION,
        return_references=_refs(*_REFS.get(n, ())),
    )
    objects = sorted(result.objects, key=lambda x: x.uuid)
    more = len(objects) > q.limit
    objects = objects[: q.limit]
    return response(
        items=[parse(x) for x in objects],
        limit=q.limit,
        total_count=count,
        cursor=_encode(objects[-1].uuid, fp) if more and objects else None,
    )


async def _delete_many(c: WeaviateAsyncClient, n: str, ids: Sequence[uuid.UUID]) -> int:
    ids = list(dict.fromkeys(ids))
    if not ids:
        return 0
    return int(
        (
            await c.collections.get(n).data.delete_many(
                where=Filter.by_id().contains_any(ids)
            )
        ).successful
    )


def _unique(ids: Sequence[uuid.UUID], name: str) -> None:
    if len(ids) != len(set(ids)):
        raise ValueError(f"{name} requires unique object IDs")


class WeaviateEntityRepository(EntityRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        o = await _get(self._client, ENTITY_COLLECTION, entity_id)
        return None if o is None else _parse_entity(o)

    async def list(self, query: EntityListRequest) -> EntityListResponse:
        fs = _direct(
            query.filter_,
            {
                "entity_type": "entity_type",
                "wikidata_id": "wikidata_id",
                "nlcr_authority_id": "nlcr_authority_id",
            },
        )
        if not is_missing(query.filter_) and (not is_missing(query.filter_.entity_id)):
            fs.append(Filter.by_id().contains_any(query.filter_.entity_id))
        return await _page(
            self._client,
            ENTITY_COLLECTION,
            query,
            fs,
            _parse_entity,
            EntityListResponse,
        )

    async def create(
        self, payload: EntityCreateRequest, context: GenericActor
    ) -> EntityResponse:
        await _require(self._client, USER_COLLECTION, context.user_id, "user")
        i = new_uuid6()
        p = _props(payload)
        p["aliases"] = p.get("aliases") or []
        await self._client.collections.get(ENTITY_COLLECTION).data.insert(
            uuid=i, properties=p, references={"user": context.user_id}
        )
        p["aliases"] = p["aliases"] or None
        return EntityResponse.model_validate(
            {**p, "entity_id": i, "user_id": context.user_id}
        )

    async def create_batch(
        self, payloads: Sequence[EntityCreateRequest], context: GenericActor
    ) -> list[EntityResponse]:
        return [await self.create(x, context) for x in payloads]

    async def patch(
        self, entity_id: uuid.UUID, payload: EntityPatchRequest, context: GenericActor
    ) -> EntityResponse | None:
        del context
        old = await self.get(entity_id)
        if old is None:
            return None
        p = _props(payload)
        if p.get("aliases") is None and "aliases" in p:
            p["aliases"] = []
        await self._client.collections.get(ENTITY_COLLECTION).data.update(
            uuid=entity_id, properties=p
        )
        if p.get("aliases") == []:
            p["aliases"] = None
        return old.model_copy(update=p)

    async def patch_batch(
        self, commands: Sequence[EntityPatchBatchItem], context: GenericActor
    ) -> list[EntityResponse | None]:
        _unique([x.entity_id for x in commands], "entity patch batch")
        return [
            await self.patch(
                x.entity_id,
                EntityPatchRequest.model_validate(_props(x, {"entity_id"})),
                context,
            )
            for x in commands
        ]

    async def delete(self, entity_id: uuid.UUID) -> bool:
        if not await _exists(self._client, ENTITY_COLLECTION, entity_id):
            return False
        for n in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            r = await self._client.collections.get(n).query.fetch_objects(
                filters=_reference("entity", [entity_id]), limit=10000
            )
            for o in r.objects:
                await self._client.collections.get(n).data.reference_replace(
                    from_uuid=o.uuid, from_property="entity", to=[]
                )
        await self._client.collections.get(ENTITY_COLLECTION).data.delete_by_id(
            entity_id
        )
        return True

    async def merge_batch(
        self,
        target_entity_id: uuid.UUID,
        source_entity_ids: Sequence[uuid.UUID],
        target_patch: EntityMergeTargetPatch | None = None,
    ) -> EntityMergeBatchResponse | None:
        raise NotImplementedError("atomic entity merge requires PostgreSQL persistence")

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID]
    ) -> EntityDeleteManyResponse:
        return EntityDeleteManyResponse(
            deleted_count=await _delete_many(
                self._client, ENTITY_COLLECTION, entity_ids
            )
        )

    async def delete_many(
        self, selector: EntityDeleteManyRequest
    ) -> EntityDeleteManyResponse:
        r = await self.list(
            EntityListRequest(filter_=selector.filter, limit=selector.limit)
        )
        return await self.delete_batch([x.entity_id for x in r.items])

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        return await _basic_search(
            self._client,
            ENTITY_COLLECTION,
            query,
            _parse_entity,
            FoundEntity,
            "entity_id",
            ("name", "aliases", "description"),
            SearchEntitiesResultListResponse,
        )


def _source_data(
    s: GenericSourceCreateRequest,
) -> tuple[uuid.UUID, dict[str, WeaviateField]]:
    library = missing_to_none(s.library)
    document = missing_to_none(s.document_id)
    page = missing_to_none(s.page_id)
    if s.source_type == SourceKind.page:
        if library is None or document is None or page is None:
            raise ValueError("page sources require library, document_id, and page_id")
        uri = page_url(library, document, page)
    elif s.source_type == SourceKind.document:
        if library is None or document is None:
            raise ValueError("document sources require library and document_id")
        uri = document_url(library, document)
    else:
        uri = str(s.url)
    return uuid.uuid5(_SOURCE_NS, f"{s.source_type.value}:{uri}"), {
        "source_type": s.source_type.value,
        "uri": uri,
        "library": library,
        "document": document,
        "page": page,
    }


class WeaviateSourceRepository(SourceRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def lookup(
        self, lookup: GenericSourceLookupRequest
    ) -> GenericSourceResponse | None:
        if not is_missing(lookup.source_id):
            o = await _get(self._client, SOURCE_COLLECTION, lookup.source_id)
            return None if o is None else _parse_source(o)
        fs: list[FilterReturn] = []
        for a, b in (
            ("source_type", "source_type"),
            ("url", "uri"),
            ("library", "library"),
            ("document_id", "document"),
            ("page_id", "page"),
        ):
            v = getattr(lookup, a)
            if not is_missing(v):
                fs.append(
                    Filter.by_property(b).equal(
                        v.value if hasattr(v, "value") else str(v) if a == "url" else v
                    )
                )
        r = await self._client.collections.get(SOURCE_COLLECTION).query.fetch_objects(
            filters=_all(fs), limit=1
        )
        return _parse_source(r.objects[0]) if r.objects else None

    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        fs = _direct(
            query.filter_,
            {
                "source_type": "source_type",
                "url": "uri",
                "library": "library",
                "document_id": "document",
                "page_id": "page",
            },
        )
        if not is_missing(query.filter_) and (not is_missing(query.filter_.source_id)):
            fs.append(Filter.by_id().contains_any(query.filter_.source_id))
        return await _page(
            self._client,
            SOURCE_COLLECTION,
            query,
            fs,
            _parse_source,
            GenericSourceListResponse,
        )

    async def get_or_create(
        self, spec: GenericSourceCreateRequest
    ) -> tuple[GenericSourceResponse, CreateResult]:
        i, p = _source_data(spec)
        o = await _get(self._client, SOURCE_COLLECTION, i)
        if o:
            return (_parse_source(o), CreateResult.EXISTING)
        await self._client.collections.get(SOURCE_COLLECTION).data.insert(
            uuid=i, properties=p
        )
        return (
            GenericSourceResponse.model_validate(
                {
                    "source_id": i,
                    "source_type": spec.source_type,
                    "url": p["uri"],
                    "library": p["library"],
                    "document_id": p["document"],
                    "page_id": p["page"],
                }
            ),
            CreateResult.CREATED,
        )

    async def get_or_create_batch(
        self, specs: Sequence[GenericSourceCreateRequest]
    ) -> list[tuple[GenericSourceResponse, CreateResult]]:
        return [await self.get_or_create(x) for x in specs]

    async def delete(self, source_id: uuid.UUID) -> bool:
        if not await _exists(self._client, SOURCE_COLLECTION, source_id):
            return False
        for n in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            r = await self._client.collections.get(n).query.fetch_objects(
                filters=_reference("source", [source_id]), limit=10000
            )
            await _delete_many(self._client, n, [x.uuid for x in r.objects])
        await self._client.collections.get(SOURCE_COLLECTION).data.delete_by_id(
            source_id
        )
        return True

    async def delete_batch(self, source_ids: Sequence[uuid.UUID]) -> int:
        return sum([await self.delete(x) for x in dict.fromkeys(source_ids)])

    async def search_documents(
        self, query: SearchDocumentsRequest
    ) -> SearchDocumentsResultListResponse:
        return await self._search_sources(
            query, SourceKind.document, FoundDocument, SearchDocumentsResultListResponse
        )

    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        return await self._search_sources(
            query, SourceKind.page, FoundPage, SearchPagesResultListResponse
        )

    async def _search_sources[F: (FoundDocument, FoundPage)](
        self,
        q: SearchDocumentsRequest | SearchPagesRequest,
        kind: SourceKind,
        found: type[F],
        response: type[GenericListResponse[F]],
    ) -> GenericListResponse[F]:
        generic = await self.list(
            GenericSourceListRequest(
                filter_=GenericSourceListFilter(source_type=[kind]), limit=10000
            )
        )
        items: list[F] = []
        for rank, x in enumerate(generic.items, 1):
            source = (
                DocumentResponse.from_generic(x)
                if kind == SourceKind.document
                else PageResponse.from_generic(x)
            )
            items.append(
                found.model_validate(
                    {**source.model_dump(), "score": 1 / (RRF_K + rank)}
                )
            )
        return response(
            items=items[: q.limit],
            limit=q.limit,
            total_count=len(items) if q.return_total_count else None,
            cursor=None,
        )


def _vectors(p: FaceCreateRequest | FacePatchRequest) -> dict[str, list[float]] | None:
    if is_missing(p.embeddings) or not p.embeddings:
        return None
    return {
        model_vector_name(FACE_VECTOR_PREFIX, str(x.model_identifier)): x.vector
        for x in p.embeddings
    }


class WeaviateFaceModelRepository(FaceModelRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def _collection(self) -> CollectionAsync[WeaviateProperties, None]:
        if not await self._client.collections.exists(FACE_MODEL_COLLECTION):
            await self._client.collections.create(FACE_MODEL_COLLECTION)
        return self._client.collections.get(FACE_MODEL_COLLECTION)

    async def register(self, payload: FaceModelRegisterRequest) -> FaceModelResponse:
        key = str(payload.model_stub)
        collection = await self._collection()
        object_id = uuid.uuid5(uuid.NAMESPACE_URL, f"peoplegator:face-model:{key}")
        existing = await _get(self._client, FACE_MODEL_COLLECTION, object_id)
        if existing is not None:
            old = FaceModelResponse.model_validate(existing.properties).embedding_dim
            if old != payload.embedding_dim:
                raise ValueError("cannot change registered model dimension")
            return FaceModelResponse(model_stub=key, embedding_dim=old)
        await collection.data.insert(
            uuid=object_id,
            properties={"model_stub": key, "embedding_dim": payload.embedding_dim},
        )
        return FaceModelResponse(
            model_stub=payload.model_stub, embedding_dim=payload.embedding_dim
        )

    async def list(self) -> FaceModelListResponse:
        collection = await self._collection()
        result = await collection.query.fetch_objects(limit=10000)
        return FaceModelListResponse(
            items=sorted(
                (
                    FaceModelResponse.model_validate(item.properties)
                    for item in result.objects
                ),
                key=lambda item: item.model_stub,
            )
        )

    async def validate(self, p: FaceCreateRequest | FacePatchRequest) -> None:
        if is_missing(p.embeddings):
            return
        models = {
            item.model_stub: item.embedding_dim for item in (await self.list()).items
        }
        for x in p.embeddings:
            dim = models.get(str(x.model_identifier))
            if dim is None:
                raise ValueError(f"face model {x.model_identifier} is not registered")
            if len(x.vector) != dim:
                raise ValueError(f"embedding dimension must be {dim}")


class WeaviateFaceRepository(FaceRepository):
    def __init__(
        self,
        client: WeaviateAsyncClient,
        models: WeaviateFaceModelRepository | None = None,
    ) -> None:
        super().__init__()
        self._client = client
        self._models = models or WeaviateFaceModelRepository(client)

    async def get(self, detection_id: uuid.UUID) -> FaceResponse | None:
        o = await _get(self._client, FACE_COLLECTION, detection_id)
        return None if o is None else _parse_face(o)

    def filters(self, f: FaceListFilter | MissingType | None) -> list[FilterReturn]:
        if f is None or is_missing(f):
            return []
        r: list[FilterReturn] = []
        if not is_missing(f.detection_id):
            r.append(Filter.by_id().contains_any(f.detection_id))
        if not is_missing(f.source_id):
            r.append(_reference("source", f.source_id))
        if not is_missing(f.entity_id):
            r.append(_reference("entity", f.entity_id))
        return r

    async def list(self, query: FaceListRequest) -> FaceListResponse:
        return await _page(
            self._client,
            FACE_COLLECTION,
            query,
            self.filters(query.filter_),
            _parse_face,
            FaceListResponse,
        )

    async def create(
        self, payload: FaceCreateRequest, context: GenericActor
    ) -> FaceResponse:
        await _require(self._client, USER_COLLECTION, context.user_id, "user")
        await _require(self._client, SOURCE_COLLECTION, payload.source_id, "source")
        await self._models.validate(payload)
        entity = missing_to_none(payload.entity_id)
        if entity:
            await _require(self._client, ENTITY_COLLECTION, entity, "entity")
        i = new_uuid6()
        props = _props(payload, {"source_id", "entity_id", "embeddings"})
        refs = {"source": payload.source_id, "user": context.user_id}
        if entity:
            refs["entity"] = entity
        await self._client.collections.get(FACE_COLLECTION).data.insert(
            uuid=i, properties=props, references=refs, vector=_vectors(payload)
        )
        return FaceResponse.model_validate(
            {
                **props,
                "detection_id": i,
                "source_id": payload.source_id,
                "entity_id": entity,
                "user_id": context.user_id,
                "embeddings": []
                if is_missing(payload.embeddings)
                else [str(x.model_identifier) for x in payload.embeddings],
            }
        )

    async def create_batch(
        self, payloads: Sequence[FaceCreateRequest], context: GenericActor
    ) -> list[FaceResponse]:
        return [await self.create(x, context) for x in payloads]

    async def patch(
        self, detection_id: uuid.UUID, payload: FacePatchRequest, context: GenericActor
    ) -> FaceResponse | None:
        del context
        old = await self.get(detection_id)
        if old is None:
            return None
        if not is_missing(payload.entity_id):
            if payload.entity_id:
                await _require(
                    self._client, ENTITY_COLLECTION, payload.entity_id, "entity"
                )
            await self._client.collections.get(FACE_COLLECTION).data.reference_replace(
                from_uuid=detection_id,
                from_property="entity",
                to=[] if payload.entity_id is None else payload.entity_id,
            )
            old = old.model_copy(update={"entity_id": payload.entity_id})
        await self._models.validate(payload)
        vectors = _vectors(payload)
        if vectors:
            await self._client.collections.get(FACE_COLLECTION).data.update(
                uuid=detection_id, vector=vectors
            )
        return old

    async def patch_batch(
        self, commands: Sequence[FacePatchBatchItem], context: GenericActor
    ) -> list[FaceResponse | None]:
        _unique([x.detection_id for x in commands], "face patch batch")
        return [
            await self.patch(
                x.detection_id,
                FacePatchRequest.model_validate(_props(x, {"detection_id"})),
                context,
            )
            for x in commands
        ]

    async def delete(self, detection_id: uuid.UUID) -> bool:
        if not await _exists(self._client, FACE_COLLECTION, detection_id):
            return False
        await self._client.collections.get(FACE_COLLECTION).data.delete_by_id(
            detection_id
        )
        return True

    async def delete_batch(self, detection_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, FACE_COLLECTION, detection_ids)

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        return await _basic_search(
            self._client,
            FACE_COLLECTION,
            query,
            _parse_face,
            FoundFace,
            "detection_id",
            ("identifier",),
            SearchFacesResultListResponse,
        )


class WeaviateTextMentionRepository(TextMentionRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, mention_id: uuid.UUID) -> TextMentionResponse | None:
        o = await _get(self._client, TEXT_MENTION_COLLECTION, mention_id)
        return None if o is None else _parse_mention(o)

    async def list(self, query: TextMentionListRequest) -> TextMentionListResponse:
        fs = (
            []
            if is_missing(query.filter_)
            else (
                []
                if is_missing(query.filter_.source_id)
                else [_reference("source", query.filter_.source_id)]
            )
            + (
                []
                if is_missing(query.filter_.entity_id)
                else [_reference("entity", query.filter_.entity_id)]
            )
        )
        return await _page(
            self._client,
            TEXT_MENTION_COLLECTION,
            query,
            fs,
            _parse_mention,
            TextMentionListResponse,
        )

    async def create(
        self, payload: TextMentionCreateRequest, context: GenericActor
    ) -> TextMentionResponse:
        del context
        await _require(self._client, SOURCE_COLLECTION, payload.source_id, "source")
        await _require(self._client, ENTITY_COLLECTION, payload.entity_id, "entity")
        i = new_uuid6()
        await self._client.collections.get(TEXT_MENTION_COLLECTION).data.insert(
            uuid=i,
            properties={
                "context": payload.context,
                **_props(payload, {"source_id", "entity_id"}),
            },
            references={"source": payload.source_id, "entity": payload.entity_id},
        )
        return TextMentionResponse.model_validate(
            {**payload.model_dump(), "mention_id": i}
        )

    async def create_batch(
        self, payloads: Sequence[TextMentionCreateRequest], context: GenericActor
    ) -> list[TextMentionResponse]:
        return [await self.create(x, context) for x in payloads]

    async def patch(
        self,
        mention_id: uuid.UUID,
        payload: TextMentionPatchRequest,
        context: GenericActor,
    ) -> TextMentionResponse | None:
        del context
        old = await self.get(mention_id)
        if old is None:
            return None
        if payload.entity_id:
            await _require(self._client, ENTITY_COLLECTION, payload.entity_id, "entity")
        await self._client.collections.get(
            TEXT_MENTION_COLLECTION
        ).data.reference_replace(
            from_uuid=mention_id,
            from_property="entity",
            to=[] if payload.entity_id is None else payload.entity_id,
        )
        return old.model_copy(update={"entity_id": payload.entity_id})

    async def patch_batch(
        self, commands: Sequence[TextMentionPatchBatchItem], context: GenericActor
    ) -> list[TextMentionResponse | None]:
        _unique([x.mention_id for x in commands], "mention patch batch")
        return [
            await self.patch(
                x.mention_id, TextMentionPatchRequest(entity_id=x.entity_id), context
            )
            for x in commands
        ]

    async def delete(self, mention_id: uuid.UUID) -> bool:
        if not await _exists(self._client, TEXT_MENTION_COLLECTION, mention_id):
            return False
        await self._client.collections.get(TEXT_MENTION_COLLECTION).data.delete_by_id(
            mention_id
        )
        return True

    async def delete_batch(self, mention_ids: Sequence[uuid.UUID]) -> int:
        return await _delete_many(self._client, TEXT_MENTION_COLLECTION, mention_ids)


class WeaviateUserRepository(UserRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        o = await _get(self._client, USER_COLLECTION, user_id)
        return None if o is None else _parse_user(o)

    async def list(self, query: UserListRequest) -> UserListResponse:
        return await _page(
            self._client,
            USER_COLLECTION,
            query,
            _direct(
                query.filter_,
                {
                    "display_name": "display_name",
                    "is_active": "is_active",
                    "external_subject": "external_subject",
                    "external_issuer": "external_issuer",
                    "email": "email",
                },
            ),
            _parse_user,
            UserListResponse,
        )

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        where = Filter.all_of(
            [
                Filter.by_property("external_issuer").equal(payload.external_issuer),
                Filter.by_property("external_subject").equal(payload.external_subject),
            ]
        )
        r = await self._client.collections.get(USER_COLLECTION).query.fetch_objects(
            filters=where, limit=1
        )
        if r.objects:
            return _parse_user(r.objects[0])
        i = new_uuid6()
        props = _props(payload)
        props["email"] = None
        await self._client.collections.get(USER_COLLECTION).data.insert(
            uuid=i, properties=props
        )
        return UserResponse.model_validate({**props, "user_id": i})

    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        old = await self.get(user_id)
        if old is None:
            return None
        props = _props(payload)
        await self._client.collections.get(USER_COLLECTION).data.update(
            uuid=user_id, properties=props
        )
        return old.model_copy(update=props)

    async def delete(self, user_id: uuid.UUID) -> bool:
        if not await _exists(self._client, USER_COLLECTION, user_id):
            return False
        for n in (ENTITY_COLLECTION, FACE_COLLECTION):
            if (
                await self._client.collections.get(n).query.fetch_objects(
                    filters=_reference("user", [user_id]), limit=1
                )
            ).objects:
                raise ValueError("cannot delete referenced user")
        await self._client.collections.get(USER_COLLECTION).data.delete_by_id(user_id)
        return True

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        return sum([await self.delete(x) for x in dict.fromkeys(user_ids)])


async def _basic_search[F: FoundItemBase](
    client: WeaviateAsyncClient,
    n: str,
    q: SearchEntitiesRequest | SearchFacesRequest,
    parse: Callable[[_StoredObject], BaseModel],
    found: type[F],
    id_field: str,
    properties: Sequence[str],
    response: type[GenericListResponse[F]],
) -> GenericListResponse[F]:
    scores: dict[uuid.UUID, float] = {}
    objects: dict[uuid.UUID, _StoredObject] = {}
    if not is_missing(q.query.text):
        for text in q.query.text:
            r = await client.collections.get(n).query.bm25(
                query=text,
                query_properties=list(properties),
                limit=10000,
                return_references=_refs(*_REFS.get(n, ())),
                include_vector=n == FACE_COLLECTION,
            )
            for rank, o in enumerate(r.objects, 1):
                objects[o.uuid] = o
                scores[o.uuid] = scores.get(o.uuid, 0) + 1 / (RRF_K + rank)
    items: list[F] = []
    for i, score in scores.items():
        items.append(
            found.model_validate({**parse(objects[i]).model_dump(), "score": score})
        )
    items.sort(key=lambda x: (-x.score, getattr(x, id_field)))
    return response(
        items=items[: q.limit],
        limit=q.limit,
        total_count=len(items) if q.return_total_count else None,
        cursor=None,
    )


def weaviate_database(client: WeaviateAsyncClient) -> Database:
    models = WeaviateFaceModelRepository(client)
    return Database(
        entities=WeaviateEntityRepository(client),
        sources=WeaviateSourceRepository(client),
        faces=WeaviateFaceRepository(client, models),
        face_models=models,
        text_mentions=WeaviateTextMentionRepository(client),
        users=WeaviateUserRepository(client),
    )


__all__ = [
    "WeaviateEntityRepository",
    "WeaviateSourceRepository",
    "WeaviateFaceRepository",
    "WeaviateFaceModelRepository",
    "WeaviateTextMentionRepository",
    "WeaviateUserRepository",
    "weaviate_database",
]
