"""Self-contained Weaviate implementation of the persistence contracts.

The adapter intentionally talks to the Weaviate v4 client directly.  It does
not use the legacy ``crud_services`` or ``weaviate_service`` data layers.
"""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.filters import FilterReturn

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
from people_gator_api.schemas.common import GenericListRequest
from people_gator_api.schemas.entities import (
    EntityDeleteManyResponse,
    EntityListRequest,
    EntityListResponse,
    EntityPatchRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelResponse,
)
from people_gator_api.schemas.faces import (
    FaceListResponse,
    FacePatchRequest,
    FaceResponse,
)
from people_gator_api.schemas.mentions import (
    TextMentionListResponse,
    TextMentionPatchRequest,
    TextMentionResponse,
)
from people_gator_api.schemas.missing import is_missing, missing_to_none
from people_gator_api.schemas.search import (
    RRF_K,
    FoundDocument,
    FoundEntity,
    FoundFace,
    FoundPage,
    SearchDocumentsResultListResponse,
    SearchEntitiesResultListResponse,
    SearchFacesResultListResponse,
    SearchPagesResultListResponse,
)
from people_gator_api.schemas.sources import (
    GenericSourceCreateRequest,
    GenericSourceListFilter,
    GenericSourceListRequest,
    GenericSourceListResponse,
    GenericSourceResponse,
    document_url,
    page_url,
)
from people_gator_api.schemas.users import UserListResponse, UserResponse
from people_gator_api.utils.uuid_utils import new_uuid6
from people_gator_api.weaviate_schema import (
    ENTITY_COLLECTION,
    FACE_COLLECTION,
    FACE_VECTOR_PREFIX,
    SOURCE_COLLECTION,
    TEXT_MENTION_COLLECTION,
    USER_COLLECTION,
    model_vector_name,
)

T = TypeVar("T", bound=BaseModel)
FACE_MODEL_COLLECTION = "FaceModel"
_SOURCE_NS = uuid.uuid5(uuid.NAMESPACE_URL, "http://peoplegator/source")
_REFS = {
    ENTITY_COLLECTION: ("user",),
    FACE_COLLECTION: ("source", "entity", "user"),
    TEXT_MENTION_COLLECTION: ("source", "entity"),
}


def _refs(*names: str) -> list[QueryReference]:
    return [QueryReference(link_on=n, return_properties=[]) for n in names]


def _ref(obj: Any, name: str, required: bool = False) -> uuid.UUID | None:
    value = (getattr(obj, "references", None) or {}).get(name)
    objects = getattr(value, "objects", None)
    result = uuid.UUID(str(objects[0].uuid)) if objects else None
    if required and result is None:
        raise ValueError(f"stored object lacks {name} reference")
    return result


def _props(model: BaseModel, exclude: set[str] = set()) -> dict[str, Any]:
    data = model.model_dump(mode="python", exclude=exclude, exclude_unset=True)
    return {
        k: (
            v.value
            if hasattr(v, "value")
            else str(v)
            if type(v).__name__ == "AnyUrl"
            else v
        )
        for k, v in data.items()
        if not is_missing(v)
    }


def _parse_user(o: Any) -> UserResponse:
    return UserResponse(user_id=o.uuid, **o.properties)


def _parse_entity(o: Any) -> EntityResponse:
    p = dict(o.properties)
    p["aliases"] = p.get("aliases") or None
    return EntityResponse(entity_id=o.uuid, user_id=_ref(o, "user", True), **p)


def _parse_source(o: Any) -> GenericSourceResponse:
    p = o.properties
    return GenericSourceResponse(
        source_id=o.uuid,
        source_type=p["source_type"],
        url=p["uri"],
        library=p.get("library"),
        document_id=p.get("document"),
        page_id=p.get("page"),
    )


def _parse_face(o: Any) -> FaceResponse:
    p = o.properties
    vectors = getattr(o, "vector", None) or {}
    prefix = model_vector_name(FACE_VECTOR_PREFIX, "x")[:-1]
    return FaceResponse(
        detection_id=o.uuid,
        identifier=p.get("identifier"),
        source_id=_ref(o, "source", True),
        entity_id=_ref(o, "entity"),
        user_id=_ref(o, "user", True),
        bounding_box=p["bounding_box"],
        keypoints=p["keypoints"],
        confidence=p["confidence"],
        embeddings=sorted(k[len(prefix) :] for k in vectors if k.startswith(prefix)),
    )


def _parse_mention(o: Any) -> TextMentionResponse:
    return TextMentionResponse(
        mention_id=o.uuid,
        source_id=_ref(o, "source", True),
        entity_id=_ref(o, "entity"),
        **o.properties,
    )


def _all(fs: Sequence[FilterReturn]) -> FilterReturn | None:
    return None if not fs else fs[0] if len(fs) == 1 else Filter.all_of(list(fs))


def _property(name: str, values: Sequence[Any]) -> FilterReturn:
    return Filter.by_property(name).contains_any(
        [v.value if hasattr(v, "value") else v for v in values]
    )


def _reference(name: str, values: Sequence[uuid.UUID]) -> FilterReturn:
    fs = [Filter.by_ref(link_on=name).by_id().equal(v) for v in values]
    return fs[0] if len(fs) == 1 else Filter.any_of(fs)


def _direct(value: Any, mapping: Mapping[str, str]) -> list[FilterReturn]:
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


async def _get(c: WeaviateAsyncClient, n: str, i: uuid.UUID) -> Any | None:
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


async def _page(
    c: WeaviateAsyncClient,
    n: str,
    q: GenericListRequest,
    fs: Sequence[FilterReturn],
    parse: Callable[[Any], T],
    response: type[Any],
) -> Any:
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
    def __init__(self, client: WeaviateAsyncClient):
        self._client = client

    async def get(self, entity_id):
        o = await _get(self._client, ENTITY_COLLECTION, entity_id)
        return None if o is None else _parse_entity(o)

    async def list(self, q):
        fs = _direct(
            q.filter_,
            {
                "entity_type": "entity_type",
                "wikidata_id": "wikidata_id",
                "nlcr_authority_id": "nlcr_authority_id",
            },
        )
        if not is_missing(q.filter_) and not is_missing(q.filter_.entity_id):
            fs.append(Filter.by_id().contains_any(q.filter_.entity_id))
        return await _page(
            self._client, ENTITY_COLLECTION, q, fs, _parse_entity, EntityListResponse
        )

    async def create(self, payload, context):
        await _require(self._client, USER_COLLECTION, context.user_id, "user")
        i = new_uuid6()
        p = _props(payload)
        p["aliases"] = p.get("aliases") or []
        await self._client.collections.get(ENTITY_COLLECTION).data.insert(
            uuid=i, properties=p, references={"user": context.user_id}
        )
        p["aliases"] = p["aliases"] or None
        return EntityResponse(entity_id=i, user_id=context.user_id, **p)

    async def create_batch(self, payloads, context):
        return [await self.create(x, context) for x in payloads]

    async def patch(self, entity_id, payload, context):
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

    async def patch_batch(self, commands, context):
        _unique([x.entity_id for x in commands], "entity patch batch")
        return [
            await self.patch(
                x.entity_id,
                EntityPatchRequest.model_validate(_props(x, {"entity_id"})),
                context,
            )
            for x in commands
        ]

    async def delete(self, entity_id):
        if not await _exists(self._client, ENTITY_COLLECTION, entity_id):
            return False
        for n in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            r = await self._client.collections.get(n).query.fetch_objects(
                filters=_reference("entity", [entity_id]), limit=10_000
            )
            for o in r.objects:
                await self._client.collections.get(n).data.reference_replace(
                    from_uuid=o.uuid, from_property="entity", to=[]
                )
        await self._client.collections.get(ENTITY_COLLECTION).data.delete_by_id(
            entity_id
        )
        return True

    async def merge_batch(self, target_entity_id, source_entity_ids, target_patch=None):
        raise NotImplementedError("atomic entity merge requires PostgreSQL persistence")

    async def delete_batch(self, ids):
        # One server-side operation keeps large cleanup jobs bounded. Weaviate
        # removes incoming references when their target is deleted.
        return await _delete_many(self._client, ENTITY_COLLECTION, ids)

    async def delete_many(self, selector):
        r = await self.list(
            EntityListRequest(filter_=selector.filter, limit=selector.limit)
        )
        return EntityDeleteManyResponse(
            deleted_count=await self.delete_batch([x.entity_id for x in r.items])
        )

    async def search(self, q):
        return await _basic_search(
            self._client,
            ENTITY_COLLECTION,
            q,
            _parse_entity,
            FoundEntity,
            "entity_id",
            ("name", "aliases", "description"),
            SearchEntitiesResultListResponse,
        )


def _source_data(s: GenericSourceCreateRequest):
    library = missing_to_none(s.library)
    document = missing_to_none(s.document_id)
    page = missing_to_none(s.page_id)
    uri = (
        page_url(library, document, page)
        if s.source_type == SourceKind.page
        else document_url(library, document)
        if s.source_type == SourceKind.document
        else str(s.url)
    )
    return uuid.uuid5(_SOURCE_NS, f"{s.source_type.value}:{uri}"), {
        "source_type": s.source_type.value,
        "uri": uri,
        "library": library,
        "document": document,
        "page": page,
    }


class WeaviateSourceRepository(SourceRepository):
    def __init__(self, client):
        self._client = client

    async def lookup(self, q):
        if not is_missing(q.source_id):
            o = await _get(self._client, SOURCE_COLLECTION, q.source_id)
            return None if o is None else _parse_source(o)
        fs = []
        for a, b in (
            ("source_type", "source_type"),
            ("url", "uri"),
            ("library", "library"),
            ("document_id", "document"),
            ("page_id", "page"),
        ):
            v = getattr(q, a)
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

    async def list(self, q):
        fs = _direct(
            q.filter_,
            {
                "source_type": "source_type",
                "url": "uri",
                "library": "library",
                "document_id": "document",
                "page_id": "page",
            },
        )
        if not is_missing(q.filter_) and not is_missing(q.filter_.source_id):
            fs.append(Filter.by_id().contains_any(q.filter_.source_id))
        return await _page(
            self._client,
            SOURCE_COLLECTION,
            q,
            fs,
            _parse_source,
            GenericSourceListResponse,
        )

    async def get_or_create(self, spec):
        i, p = _source_data(spec)
        o = await _get(self._client, SOURCE_COLLECTION, i)
        if o:
            return _parse_source(o), CreateResult.EXISTING
        await self._client.collections.get(SOURCE_COLLECTION).data.insert(
            uuid=i, properties=p
        )
        return GenericSourceResponse(
            source_id=i,
            source_type=spec.source_type,
            url=p["uri"],
            library=p["library"],
            document_id=p["document"],
            page_id=p["page"],
        ), CreateResult.CREATED

    async def get_or_create_batch(self, specs):
        return [await self.get_or_create(x) for x in specs]

    async def delete(self, i):
        if not await _exists(self._client, SOURCE_COLLECTION, i):
            return False
        for n in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            r = await self._client.collections.get(n).query.fetch_objects(
                filters=_reference("source", [i]), limit=10_000
            )
            await _delete_many(self._client, n, [x.uuid for x in r.objects])
        await self._client.collections.get(SOURCE_COLLECTION).data.delete_by_id(i)
        return True

    async def delete_batch(self, ids):
        return sum([await self.delete(x) for x in dict.fromkeys(ids)])

    async def search_documents(self, q):
        return await self._search_sources(
            q, SourceKind.document, FoundDocument, SearchDocumentsResultListResponse
        )

    async def search_pages(self, q):
        return await self._search_sources(
            q, SourceKind.page, FoundPage, SearchPagesResultListResponse
        )

    async def _search_sources(self, q, kind, found, response):
        generic = await self.list(
            GenericSourceListRequest(
                filter_=GenericSourceListFilter(source_type=[kind]), limit=10_000
            )
        )
        items = []
        for rank, x in enumerate(generic.items, 1):
            items.append(
                found(**found.from_generic(x).model_dump(), score=1 / (RRF_K + rank))
            )
        return response(
            items=items[: q.limit],
            limit=q.limit,
            total_count=len(items) if q.return_total_count else None,
            cursor=None,
        )


def _vectors(p):
    if is_missing(p.embeddings) or not p.embeddings:
        return None
    return {
        model_vector_name(FACE_VECTOR_PREFIX, str(x.model_identifier)): x.vector
        for x in p.embeddings
    }


class WeaviateFaceModelRepository(FaceModelRepository):
    def __init__(self, client):
        self._client = client

    async def _collection(self):
        if not await self._client.collections.exists(FACE_MODEL_COLLECTION):
            await self._client.collections.create(FACE_MODEL_COLLECTION)
        return self._client.collections.get(FACE_MODEL_COLLECTION)

    async def register(self, p):
        key = str(p.model_stub)
        collection = await self._collection()
        object_id = uuid.uuid5(uuid.NAMESPACE_URL, f"peoplegator:face-model:{key}")
        existing = await collection.query.fetch_object_by_id(object_id)
        if existing is not None:
            old = int(existing.properties["embedding_dim"])
            if old != p.embedding_dim:
                raise ValueError("cannot change registered model dimension")
            return FaceModelResponse(model_stub=key, embedding_dim=old)
        await collection.data.insert(
            uuid=object_id,
            properties={"model_stub": key, "embedding_dim": p.embedding_dim},
        )
        return FaceModelResponse(model_stub=p.model_stub, embedding_dim=p.embedding_dim)

    async def list(self):
        collection = await self._collection()
        result = await collection.query.fetch_objects(limit=10_000)
        return FaceModelListResponse(
            items=sorted(
                (FaceModelResponse(**item.properties) for item in result.objects),
                key=lambda item: item.model_stub,
            )
        )

    async def validate(self, p):
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
    def __init__(self, client, models=None):
        self._client = client
        self._models = models or WeaviateFaceModelRepository(client)

    async def get(self, i):
        o = await _get(self._client, FACE_COLLECTION, i)
        return None if o is None else _parse_face(o)

    def filters(self, f):
        if f is None or is_missing(f):
            return []
        r = []
        if not is_missing(f.detection_id):
            r.append(Filter.by_id().contains_any(f.detection_id))
        if not is_missing(f.source_id):
            r.append(_reference("source", f.source_id))
        if not is_missing(f.entity_id):
            r.append(_reference("entity", f.entity_id))
        return r

    async def list(self, q):
        return await _page(
            self._client,
            FACE_COLLECTION,
            q,
            self.filters(q.filter_),
            _parse_face,
            FaceListResponse,
        )

    async def create(self, p, context):
        await _require(self._client, USER_COLLECTION, context.user_id, "user")
        await _require(self._client, SOURCE_COLLECTION, p.source_id, "source")
        await self._models.validate(p)
        entity = missing_to_none(p.entity_id)
        if entity:
            await _require(self._client, ENTITY_COLLECTION, entity, "entity")
        i = new_uuid6()
        props = _props(p, {"source_id", "entity_id", "embeddings"})
        refs = {"source": p.source_id, "user": context.user_id}
        if entity:
            refs["entity"] = entity
        await self._client.collections.get(FACE_COLLECTION).data.insert(
            uuid=i, properties=props, references=refs, vector=_vectors(p)
        )
        return FaceResponse(
            detection_id=i,
            source_id=p.source_id,
            entity_id=entity,
            user_id=context.user_id,
            embeddings=[]
            if is_missing(p.embeddings)
            else [str(x.model_identifier) for x in p.embeddings],
            **props,
        )

    async def create_batch(self, payloads, context):
        return [await self.create(x, context) for x in payloads]

    async def patch(self, i, p, context):
        del context
        old = await self.get(i)
        if old is None:
            return None
        if not is_missing(p.entity_id):
            if p.entity_id:
                await _require(self._client, ENTITY_COLLECTION, p.entity_id, "entity")
            await self._client.collections.get(FACE_COLLECTION).data.reference_replace(
                from_uuid=i,
                from_property="entity",
                to=[] if p.entity_id is None else p.entity_id,
            )
            old = old.model_copy(update={"entity_id": p.entity_id})
        await self._models.validate(p)
        vectors = _vectors(p)
        if vectors:
            await self._client.collections.get(FACE_COLLECTION).data.update(
                uuid=i, vector=vectors
            )
        return old

    async def patch_batch(self, commands, context):
        _unique([x.detection_id for x in commands], "face patch batch")
        return [
            await self.patch(
                x.detection_id,
                FacePatchRequest.model_validate(_props(x, {"detection_id"})),
                context,
            )
            for x in commands
        ]

    async def delete(self, i):
        if not await _exists(self._client, FACE_COLLECTION, i):
            return False
        await self._client.collections.get(FACE_COLLECTION).data.delete_by_id(i)
        return True

    async def delete_batch(self, ids):
        return await _delete_many(self._client, FACE_COLLECTION, ids)

    async def search(self, q):
        return await _basic_search(
            self._client,
            FACE_COLLECTION,
            q,
            _parse_face,
            FoundFace,
            "detection_id",
            ("identifier",),
            SearchFacesResultListResponse,
        )


class WeaviateTextMentionRepository(TextMentionRepository):
    def __init__(self, client):
        self._client = client

    async def get(self, i):
        o = await _get(self._client, TEXT_MENTION_COLLECTION, i)
        return None if o is None else _parse_mention(o)

    async def list(self, q):
        fs = (
            []
            if is_missing(q.filter_)
            else (
                []
                if is_missing(q.filter_.source_id)
                else [_reference("source", q.filter_.source_id)]
            )
            + (
                []
                if is_missing(q.filter_.entity_id)
                else [_reference("entity", q.filter_.entity_id)]
            )
        )
        return await _page(
            self._client,
            TEXT_MENTION_COLLECTION,
            q,
            fs,
            _parse_mention,
            TextMentionListResponse,
        )

    async def create(self, p, context):
        del context
        await _require(self._client, SOURCE_COLLECTION, p.source_id, "source")
        await _require(self._client, ENTITY_COLLECTION, p.entity_id, "entity")
        i = new_uuid6()
        await self._client.collections.get(TEXT_MENTION_COLLECTION).data.insert(
            uuid=i,
            properties=_props(p, {"source_id", "entity_id"}),
            references={"source": p.source_id, "entity": p.entity_id},
        )
        return TextMentionResponse(mention_id=i, **_props(p))

    async def create_batch(self, payloads, context):
        return [await self.create(x, context) for x in payloads]

    async def patch(self, i, p, context):
        del context
        old = await self.get(i)
        if old is None:
            return None
        if p.entity_id:
            await _require(self._client, ENTITY_COLLECTION, p.entity_id, "entity")
        await self._client.collections.get(
            TEXT_MENTION_COLLECTION
        ).data.reference_replace(
            from_uuid=i,
            from_property="entity",
            to=[] if p.entity_id is None else p.entity_id,
        )
        return old.model_copy(update={"entity_id": p.entity_id})

    async def patch_batch(self, commands, context):
        _unique([x.mention_id for x in commands], "mention patch batch")
        return [
            await self.patch(
                x.mention_id, TextMentionPatchRequest(entity_id=x.entity_id), context
            )
            for x in commands
        ]

    async def delete(self, i):
        if not await _exists(self._client, TEXT_MENTION_COLLECTION, i):
            return False
        await self._client.collections.get(TEXT_MENTION_COLLECTION).data.delete_by_id(i)
        return True

    async def delete_batch(self, ids):
        return await _delete_many(self._client, TEXT_MENTION_COLLECTION, ids)


class WeaviateUserRepository(UserRepository):
    def __init__(self, client):
        self._client = client

    async def get(self, i):
        o = await _get(self._client, USER_COLLECTION, i)
        return None if o is None else _parse_user(o)

    async def list(self, q):
        return await _page(
            self._client,
            USER_COLLECTION,
            q,
            _direct(
                q.filter_,
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

    async def get_or_create(self, p):
        where = Filter.all_of(
            [
                Filter.by_property("external_issuer").equal(p.external_issuer),
                Filter.by_property("external_subject").equal(p.external_subject),
            ]
        )
        r = await self._client.collections.get(USER_COLLECTION).query.fetch_objects(
            filters=where, limit=1
        )
        if r.objects:
            return _parse_user(r.objects[0])
        i = new_uuid6()
        props = _props(p)
        props["email"] = None
        await self._client.collections.get(USER_COLLECTION).data.insert(
            uuid=i, properties=props
        )
        return UserResponse(user_id=i, **props)

    async def patch(self, i, p):
        old = await self.get(i)
        if old is None:
            return None
        props = _props(p)
        await self._client.collections.get(USER_COLLECTION).data.update(
            uuid=i, properties=props
        )
        return old.model_copy(update=props)

    async def delete(self, i):
        if not await _exists(self._client, USER_COLLECTION, i):
            return False
        for n in (ENTITY_COLLECTION, FACE_COLLECTION):
            if (
                await self._client.collections.get(n).query.fetch_objects(
                    filters=_reference("user", [i]), limit=1
                )
            ).objects:
                raise ValueError("cannot delete referenced user")
        await self._client.collections.get(USER_COLLECTION).data.delete_by_id(i)
        return True

    async def delete_batch(self, ids):
        return sum([await self.delete(x) for x in dict.fromkeys(ids)])


async def _basic_search(client, n, q, parse, found, id_field, properties, response):
    # BM25 is backend-native as allowed by the contract. We fuse its one-based
    # ranks with RRF; face-vector searches are issued against the named slot.
    scores = {}
    objects = {}
    if not is_missing(q.query.text):
        for text in q.query.text:
            r = await client.collections.get(n).query.bm25(
                query=text,
                query_properties=list(properties),
                limit=10_000,
                return_references=_refs(*_REFS.get(n, ())),
                include_vector=n == FACE_COLLECTION,
            )
            for rank, o in enumerate(r.objects, 1):
                objects[o.uuid] = o
                scores[o.uuid] = scores.get(o.uuid, 0) + 1 / (RRF_K + rank)
    items = []
    for i, score in scores.items():
        items.append(found(**parse(objects[i]).model_dump(), score=score))
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
