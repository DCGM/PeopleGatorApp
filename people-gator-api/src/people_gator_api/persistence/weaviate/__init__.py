"""Self-contained Weaviate implementation of the persistence contracts.

This package owns the Weaviate adapter, client construction, collection schemas,
and backend query helpers. Application lifecycle lives in database_service.
The contract adapter talks to the v4 client directly.
"""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, nullcontext
from collections import defaultdict
from datetime import datetime, timezone
from weakref import WeakValueDictionary
import base64
import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from typing import Literal, Protocol, overload

from pydantic import BaseModel
from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter, QueryReference
from weaviate.collections.classes.aggregate import GroupByAggregate
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
from people_gator_api.schemas.enums import SourceKind, EntityLinkState
from people_gator_api.schemas.entity_links import EntityLinkStats
from people_gator_api.persistence.entity_links import create_link_state, link_transition
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
from people_gator_api.schemas.missing import (
    MISSING,
    MissingType,
    is_missing,
    missing_to_none,
)
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


def _require_postgres_for_evidence(f, *, allow_document_scope=False):
    if f is not None and not is_missing(f) and any(
        not is_missing(getattr(f, field)) for field in (
            "evidence_library", "evidence_source_id", "evidence_touched_from", "evidence_touched_to",
            "evidence_touched_by_user_id", "evidence_touched_by_api_key_id",
            *(() if allow_document_scope else ("document_source_id",)))):
        raise NotImplementedError("Annotation edit filters require PostgreSQL")


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
            "name": p.get("name"),
        }
    )


def _parse_face(o: _StoredObject) -> FaceResponse:
    prefix = model_vector_name(FACE_VECTOR_PREFIX, "x")[:-1]
    return FaceResponse.model_validate(
        {
            **{
                key: value
                for key, value in o.properties.items()
                if key not in ("linked_entity_id", "annotation_source_id")
            },
            "entity_link_state": o.properties.get("entity_link_state")
            or ("automatic" if _ref(o, "entity") else None),
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
            **{
                key: value
                for key, value in o.properties.items()
                if key not in ("linked_entity_id", "annotation_source_id")
            },
            "entity_link_state": o.properties.get("entity_link_state")
            or ("automatic" if _ref(o, "entity") else None),
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


def _require_default_sort(query: object) -> None:
    """Weaviate keeps only the default orders; explicit sorts are rejected."""
    if getattr(query, "sort", None) is None:
        return
    field, direction = getattr(query, "effective_sort")()
    if getattr(type(query), "is_search", lambda: False)() and (field, direction) == ("relevance", "desc"):
        return
    raise NotImplementedError("sorting is not supported by the Weaviate backend")


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
    items = [parse(x) for x in objects]
    if n in (ENTITY_COLLECTION, SOURCE_COLLECTION):
        await _attach_stats(c, items, entities=n == ENTITY_COLLECTION)
    return response(
        items=items,
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


_LINK_LOCKS: WeakValueDictionary[tuple[str, uuid.UUID], asyncio.Lock] = (
    WeakValueDictionary()
)


def _link_lock(collection, item_id):
    key = (collection, item_id)
    lock = _LINK_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LINK_LOCKS[key] = lock
    return lock


async def _scan(client, name, filters=None):
    """Page through IDs without a fixed 10,000-record truncation."""
    cursor = None
    while True:
        result = await client.collections.get(name).query.fetch_objects(
            filters=filters,
            after=cursor,
            limit=500,
            return_references=_refs(*_REFS.get(name, ())),
        )
        if not result.objects:
            return
        yield result.objects
        next_id = result.objects[-1].uuid
        if next_id == cursor or len(result.objects) < 500:
            return
        cursor = next_id


async def _touch(client, ids, context):
    properties = {
        "last_touched_at": datetime.now(timezone.utc),
        "last_touched_by_user_id": str(context.user_id),
        "last_touched_by_api_key_id": str(context.api_key_id)
        if getattr(context, "api_key_id", None)
        else None,
    }
    for entity_id in set(ids) - {None}:
        await client.collections.get(ENTITY_COLLECTION).data.update(
            uuid=entity_id, properties=properties
        )


def _link_properties(values):
    entity, state, verifier, verified_at = values
    return {
        "linked_entity_id": str(entity) if entity else None,
        "entity_link_state": state.value if state else None,
        "entity_link_verified_by_user_id": str(verifier) if verifier else None,
        "entity_link_verified_at": verified_at,
    }


async def _replace_link(client, name, stored, values, vectors=None):
    # Weaviate PATCH adds references; replacing the complete object is required
    # to atomically replace/remove a link with its verification metadata.
    refs = {
        field: value
        for field in _REFS[name]
        if (value := _ref(stored, field)) is not None and field != "entity"
    }
    if values[0] is not None:
        refs["entity"] = values[0]
    named_vectors = {**stored.vector, **(vectors or {})}
    await client.collections.get(name).data.replace(
        uuid=stored.uuid,
        properties={**stored.properties, **_link_properties(values)},
        references=refs,
        vector=named_vectors or None,
    )


async def _patch_annotation(
    client, name, item_id, payload, context, *, models=None, locked=False
):
    async with nullcontext() if locked else _link_lock(name, item_id):
        stored = await _get(client, name, item_id)
        if stored is None:
            return None
        old = (_parse_face if name == FACE_COLLECTION else _parse_mention)(stored)
        await _require(client, USER_COLLECTION, context.user_id, "actor user")
        values = link_transition(old, payload, context)
        if values[0] is not None:
            await _require(client, ENTITY_COLLECTION, values[0], "entity")
        if models is not None:
            await models.validate(payload)
        vectors = _vectors(payload) if models is not None else None
        old_values = (
            old.entity_id,
            old.entity_link_state,
            old.entity_link_verified_by_user_id,
            old.entity_link_verified_at,
        )
        changed = values != old_values
        # References and link metadata are sent in a single object update.
        if changed or vectors:
            await _replace_link(client, name, stored, values, vectors)
            await _touch(client, [old.entity_id, values[0]], context)
        fields = dict(
            zip(
                (
                    "entity_id",
                    "entity_link_state",
                    "entity_link_verified_by_user_id",
                    "entity_link_verified_at",
                ),
                values,
            )
        )
        if models is not None and not is_missing(payload.embeddings):
            fields["embeddings"] = sorted(
                set(old.embeddings)
                | {item.model_identifier for item in payload.embeddings}
            )
        return old.model_copy(update=fields)


async def _patch_annotations(client, name, commands, context, *, models=None):
    id_field = "detection_id" if name == FACE_COLLECTION else "mention_id"
    ids = [getattr(command, id_field) for command in commands]
    _unique(ids, "annotation patch batch")
    async with AsyncExitStack() as locks:
        for item_id in sorted(ids):
            await locks.enter_async_context(_link_lock(name, item_id))
        # Preflight the complete batch before writing any object.
        for command in commands:
            if not is_missing(command.entity_id) and command.entity_id is not None:
                await _require(client, ENTITY_COLLECTION, command.entity_id, "entity")
            stored = await _get(client, name, getattr(command, id_field))
            if stored is not None:
                old = (_parse_face if name == FACE_COLLECTION else _parse_mention)(
                    stored
                )
                link_transition(old, command, context)
            if models is not None:
                await models.validate(command)
        return [
            await _patch_annotation(
                client,
                name,
                getattr(command, id_field),
                command,
                context,
                models=models,
                locked=True,
            )
            for command in commands
        ]


async def _delete_annotations(client, name, ids, context):
    unique = list(dict.fromkeys(ids))
    if not unique:
        return 0
    entities = set()
    async for objects in _scan(client, name, Filter.by_id().contains_any(unique)):
        entities.update(_ref(obj, "entity") for obj in objects)
    deleted = await _delete_many(client, name, unique)
    if deleted:
        await _touch(client, entities, context)
    return deleted


async def _document_scope(client, documents):
    """Internal source IDs, including direct document annotations."""
    ids = set()
    for document_id in documents:
        stored = await _get(client, SOURCE_COLLECTION, document_id)
        if stored is None or stored.properties.get("source_type") != "document":
            continue
        ids.add(document_id)
        p = stored.properties
        filters = Filter.all_of(
            [
                Filter.by_property("source_type").equal("page"),
                Filter.by_property("library").equal(p["library"]),
                Filter.by_property("document").equal(p["document"]),
            ]
        )
        async for objects in _scan(client, SOURCE_COLLECTION, filters):
            ids.update(
                o.uuid
                for o in objects
                if o.properties.get("library") == p["library"]
                and str(o.properties.get("document")) == str(p["document"])
            )
    return ids


async def _evidence_ids(client, filter_values, *, entities):
    """Resolve matching entity/source IDs before the final paginated query."""
    states = missing_to_none(filter_values.entity_link_state)
    detection_ids = missing_to_none(filter_values.detection_id)
    mention_ids = missing_to_none(filter_values.mention_id)
    source_ids = (
        missing_to_none(getattr(filter_values, "source_id", MISSING))
        if entities
        else None
    )
    document_ids = (
        missing_to_none(getattr(filter_values, "document_source_id", MISSING))
        if entities
        else None
    )
    doc_sources = (
        await _document_scope(client, document_ids)
        if document_ids is not None
        else None
    )
    entity_ids = missing_to_none(filter_values.entity_id) if not entities else None
    matches = []
    for name, ids in (
        (FACE_COLLECTION, detection_ids),
        (TEXT_MENTION_COLLECTION, mention_ids),
    ):
        fs = []
        if states is not None:
            fs.append(_property("entity_link_state", [s.value for s in states]))
        if ids is not None:
            fs.append(Filter.by_id().contains_any(ids))
        if source_ids is not None:
            fs.append(_reference("source", source_ids))
        if doc_sources is not None:
            fs.append(_reference("source", list(doc_sources)))
        if entity_ids is not None:
            fs.append(_reference("entity", entity_ids))
        found = set()
        async for objects in _scan(client, name, _all(fs)):
            for obj in objects:
                value = _ref(obj, "entity" if entities else "source")
                if value is not None:
                    found.add(value)
        matches.append(found)
    if detection_ids is not None and mention_ids is not None:
        result = matches[0] & matches[1]
    elif detection_ids is not None:
        result = matches[0]
    elif mention_ids is not None:
        result = matches[1]
    else:
        result = matches[0] | matches[1]
    if not entities:
        # A document also matches annotations on its registered pages.
        async for objects in _scan(
            client,
            SOURCE_COLLECTION,
            Filter.by_property("source_type").equal("document"),
        ):
            for obj in objects:
                if result & await _document_scope(client, [obj.uuid]):
                    result.add(obj.uuid)
    return result


async def _presence_filters(client, f, *, entities):
    if f is None or is_missing(f):
        return []
    filters = []
    names = (
        ("has_mentions", (TEXT_MENTION_COLLECTION,)),
        ("has_detections" if entities else "has_faces", (FACE_COLLECTION,)),
    )
    if not entities:
        names += (("has_entities", (FACE_COLLECTION, TEXT_MENTION_COLLECTION)),)
    for field, collections in names:
        expected = missing_to_none(getattr(f, field, MISSING))
        if expected is None:
            continue
        ids = set()
        for name in collections:
            async for objects in _scan(client, name):
                for obj in objects:
                    if field == "has_entities" and _ref(obj, "entity") is None:
                        continue
                    item_id = _ref(obj, "entity" if entities else "source")
                    if item_id is not None:
                        ids.add(item_id)
        predicate = Filter.by_id().contains_any(list(ids) or [uuid.UUID(int=0)])
        filters.append(predicate if expected else ~predicate)
    if entities:
        for field, operator in (
            ("last_touched_from", "greater_or_equal"),
            ("last_touched_to", "less_or_equal"),
        ):
            value = missing_to_none(getattr(f, field, MISSING))
            if value is not None:
                filters.append(
                    getattr(Filter.by_property("last_touched_at"), operator)(value)
                )
        for field in ("last_touched_by_user_id", "last_touched_by_api_key_id"):
            value = missing_to_none(getattr(f, field, MISSING))
            if value is not None:
                filters.append(_property(field, [str(item) for item in value]))
    return filters


async def _attach_stats(client, items, *, entities=False):
    """Grouped server aggregates; only response-page owners enter the grouping."""
    if not items:
        return
    owners = {item.entity_id if entities else item.source_id: item for item in items}
    source_owners = defaultdict(set)
    if not entities:
        documents = {}
        for owner, item in owners.items():
            source_owners[owner].add(owner)
            if item.source_type == SourceKind.document:
                documents[(item.library, str(item.document_id))] = owner
        if documents:
            predicate = Filter.all_of(
                [
                    Filter.by_property("source_type").equal("page"),
                    Filter.any_of(
                        [
                            Filter.all_of(
                                [
                                    Filter.by_property("library").equal(library),
                                    Filter.by_property("document").equal(document),
                                ]
                            )
                            for library, document in documents
                        ]
                    ),
                ]
            )
            async for objects in _scan(client, SOURCE_COLLECTION, predicate):
                for obj in objects:
                    owner = documents.get(
                        (
                            obj.properties.get("library"),
                            str(obj.properties.get("document")),
                        )
                    )
                    if owner is not None:
                        source_owners[obj.uuid].add(owner)
    key = "linked_entity_id" if entities else "annotation_source_id"
    keys = list(owners) if entities else list(source_owners)
    stats = {owner: EntityLinkStats() for owner in owners}
    for name, kind in (
        (FACE_COLLECTION, "faces"),
        (TEXT_MENTION_COLLECTION, "mentions"),
    ):
        for state in (*EntityLinkState, None):
            predicate = _property(key, [str(k) for k in keys])
            if state is not None:
                predicate = predicate & Filter.by_property("entity_link_state").equal(
                    state.value
                )
            result = await client.collections.get(name).aggregate.over_all(
                filters=predicate,
                group_by=GroupByAggregate(prop=key, limit=len(keys)),
                total_count=True,
            )
            for group in result.groups:
                group_key = uuid.UUID(str(group.grouped_by.value))
                for owner in {group_key} if entities else source_owners[group_key]:
                    counts = getattr(stats[owner], kind)
                    field = state.value if state is not None else "unassigned"
                    if state is None:
                        counts.total += group.total_count or 0
                        counts.unassigned = (
                            counts.total
                            - counts.automatic
                            - counts.manual
                            - counts.verified
                        )
                    else:
                        setattr(
                            counts,
                            field,
                            getattr(counts, field) + (group.total_count or 0),
                        )
    for owner, item in owners.items():
        item.entity_link_stats = stats[owner]


class WeaviateEntityRepository(EntityRepository):
    def __init__(self, client: WeaviateAsyncClient) -> None:
        super().__init__()
        self._client = client

    async def get(self, entity_id: uuid.UUID) -> EntityResponse | None:
        o = await _get(self._client, ENTITY_COLLECTION, entity_id)
        if o is None:
            return None
        result = _parse_entity(o)
        await _attach_stats(self._client, [result], entities=True)
        return result

    async def list(self, query: EntityListRequest) -> EntityListResponse:
        _require_default_sort(query)
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
        _require_postgres_for_evidence(query.filter_, allow_document_scope=True)
        f = missing_to_none(query.filter_)
        if f is not None and any(
            not is_missing(getattr(f, field))
            for field in (
                "entity_link_state",
                "source_id",
                "document_source_id",
                "detection_id",
                "mention_id",
            )
        ):
            ids = await _evidence_ids(self._client, f, entities=True)
            fs.append(Filter.by_id().contains_any(list(ids) or [uuid.UUID(int=0)]))
        fs.extend(await _presence_filters(self._client, query.filter_, entities=True))
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
        if not is_missing(payload.thumbnail_face_id):
            raise ValueError("persisted person thumbnails require PostgreSQL")
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
        if any(not is_missing(x.thumbnail_face_id) for x in commands):
            raise ValueError("persisted person thumbnails require PostgreSQL")
        return [
            await self.patch(
                x.entity_id,
                EntityPatchRequest.model_validate(_props(x, {"entity_id"})),
                context,
            )
            for x in commands
        ]

    async def delete(self, entity_id: uuid.UUID, *, context: GenericActor) -> bool:
        if not await _exists(self._client, ENTITY_COLLECTION, entity_id):
            return False
        for name in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            async for objects in _scan(
                self._client, name, _reference("entity", [entity_id])
            ):
                for obj in objects:
                    async with _link_lock(name, obj.uuid):
                        stored = await _get(self._client, name, obj.uuid)
                        if stored is not None:
                            await _replace_link(
                                self._client, name, stored, (None, None, None, None)
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
        *,
        context: GenericActor,
    ) -> EntityMergeBatchResponse | None:
        _unique(list(source_entity_ids), "entity merge batch")
        if target_entity_id in source_entity_ids:
            raise ValueError("source and target must differ")
        target = await self.get(target_entity_id)
        sources = [await self.get(item_id) for item_id in source_entity_ids]
        if target is None or any(item is None for item in sources):
            return None
        counts = []
        for name in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            count = 0
            async for objects in _scan(
                self._client, name, _reference("entity", source_entity_ids)
            ):
                for obj in objects:
                    patch = (
                        FacePatchRequest(
                            entity_id=target_entity_id,
                            entity_link_state=EntityLinkState.manual,
                        )
                        if name == FACE_COLLECTION
                        else TextMentionPatchRequest(
                            entity_id=target_entity_id,
                            entity_link_state=EntityLinkState.manual,
                        )
                    )
                    await _patch_annotation(
                        self._client, name, obj.uuid, patch, context
                    )
                    count += 1
            counts.append(count)
        aliases = list(
            dict.fromkeys(
                [
                    *(target.aliases or []),
                    *(alias for source in sources for alias in (source.aliases or [])),
                ]
            )
        )
        fields = target_patch.model_dump() if target_patch else {}
        await self.patch(
            target_entity_id, EntityPatchRequest(aliases=aliases, **fields), context
        )
        for item_id in source_entity_ids:
            await self.delete(item_id, context=context)
        return EntityMergeBatchResponse(
            source_entity_ids=list(source_entity_ids),
            target_entity_id=target_entity_id,
            faces_reassigned=counts[0],
            text_mentions_reassigned=counts[1],
            merged_entity=await self.get(target_entity_id),
        )

    async def delete_batch(
        self, entity_ids: Sequence[uuid.UUID], *, context: GenericActor
    ) -> EntityDeleteManyResponse:
        unique = list(dict.fromkeys(entity_ids))
        if not unique:
            return EntityDeleteManyResponse(deleted_count=0)
        for name in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            async for objects in _scan(
                self._client, name, _reference("entity", unique)
            ):
                for obj in objects:
                    async with _link_lock(name, obj.uuid):
                        stored = await _get(self._client, name, obj.uuid)
                        if stored is not None:
                            await _replace_link(
                                self._client, name, stored, (None, None, None, None)
                            )
        return EntityDeleteManyResponse(
            deleted_count=await _delete_many(self._client, ENTITY_COLLECTION, unique)
        )

    async def delete_many(
        self, selector: EntityDeleteManyRequest, *, context: GenericActor
    ) -> EntityDeleteManyResponse:
        r = await self.list(
            EntityListRequest(filter_=selector.filter, limit=selector.limit)
        )
        return await self.delete_batch([x.entity_id for x in r.items], context=context)

    async def search(
        self, query: SearchEntitiesRequest
    ) -> SearchEntitiesResultListResponse:
        _require_default_sort(query)
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
        "name": s.name,
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
            if o is None:
                return None
            result = _parse_source(o)
            await _attach_stats(self._client, [result])
            return result
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
        if not r.objects:
            return None
        result = _parse_source(r.objects[0])
        await _attach_stats(self._client, [result])
        return result

    async def list(self, query: GenericSourceListRequest) -> GenericSourceListResponse:
        _require_default_sort(query)
        if not is_missing(query.filter_) and any(not is_missing(getattr(query.filter_, name)) for name in (
            "last_touched_from", "last_touched_to", "last_touched_by_user_id", "last_touched_by_api_key_id", "has_unassigned_faces",
        )):
            raise NotImplementedError("Source processing filters require PostgreSQL")
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
        _require_postgres_for_evidence(query.filter_)
        f = missing_to_none(query.filter_)
        if f is not None and any(
            not is_missing(getattr(f, field))
            for field in (
                "entity_link_state",
                "entity_id",
                "detection_id",
                "mention_id",
            )
        ):
            ids = await _evidence_ids(self._client, f, entities=False)
            fs.append(Filter.by_id().contains_any(list(ids) or [uuid.UUID(int=0)]))
        fs.extend(await _presence_filters(self._client, query.filter_, entities=False))
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
            result = _parse_source(o)
            await _attach_stats(self._client, [result])
            return (result, CreateResult.EXISTING)
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
                    "name": p.get("name"),
                }
            ),
            CreateResult.CREATED,
        )

    async def get_or_create_batch(
        self, specs: Sequence[GenericSourceCreateRequest]
    ) -> list[tuple[GenericSourceResponse, CreateResult]]:
        return [await self.get_or_create(x) for x in specs]

    async def delete(self, source_id: uuid.UUID, *, context: GenericActor) -> bool:
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

    async def delete_batch(
        self, source_ids: Sequence[uuid.UUID], *, context: GenericActor
    ) -> int:
        return sum(
            [await self.delete(x, context=context) for x in dict.fromkeys(source_ids)]
        )

    async def search_documents(
        self, query: SearchDocumentsRequest
    ) -> SearchDocumentsResultListResponse:
        _require_default_sort(query)
        return await self._search_sources(
            query, SourceKind.document, FoundDocument, SearchDocumentsResultListResponse
        )

    async def search_pages(
        self, query: SearchPagesRequest
    ) -> SearchPagesResultListResponse:
        _require_default_sort(query)
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
        query = GenericSourceListRequest(
            filter_=q.filter_.to_generic()
            if q.filter_ is not None
            else GenericSourceListFilter(source_type=[kind]),
            limit=q.limit,
            return_total_count=q.return_total_count,
        )
        fingerprint = _fingerprint(q)
        after = _decode(q.cursor, fingerprint)
        list_fingerprint = _fingerprint(query)
        query.cursor = _encode(after, list_fingerprint) if after else None
        generic = await self.list(query)
        items = []
        for rank, item in enumerate(generic.items, 1):
            source = (
                DocumentResponse.from_generic(item)
                if kind == SourceKind.document
                else PageResponse.from_generic(item)
            )
            items.append(
                found.model_validate(
                    {**source.model_dump(), "score": 1 / (RRF_K + rank)}
                )
            )
        next_id = _decode(generic.cursor, list_fingerprint) if generic.cursor else None
        return response(
            items=items,
            limit=q.limit,
            total_count=generic.total_count,
            cursor=_encode(next_id, fingerprint) if next_id else None,
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
        _require_postgres_for_evidence(f)
        if f is None or is_missing(f):
            return []
        r: list[FilterReturn] = []
        if not is_missing(f.entity_link_state):
            r.append(
                _property(
                    "entity_link_state", [state.value for state in f.entity_link_state]
                )
            )
        if not is_missing(f.detection_id):
            r.append(Filter.by_id().contains_any(f.detection_id))
        if not is_missing(f.source_id):
            r.append(_reference("source", f.source_id))
        if not is_missing(f.entity_id):
            r.append(_reference("entity", f.entity_id))
        return r

    async def list(self, query: FaceListRequest) -> FaceListResponse:
        _require_default_sort(query)
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
        props.update(_link_properties((entity, create_link_state(payload), None, None)))
        props["annotation_source_id"] = str(payload.source_id)
        refs = {"source": payload.source_id, "user": context.user_id}
        if entity:
            refs["entity"] = entity
        await self._client.collections.get(FACE_COLLECTION).data.insert(
            uuid=i, properties=props, references=refs, vector=_vectors(payload)
        )
        await _touch(self._client, [entity], context)
        return FaceResponse.model_validate(
            {
                **{
                    key: value
                    for key, value in props.items()
                    if key not in ("linked_entity_id", "annotation_source_id")
                },
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
        return await _patch_annotation(
            self._client,
            FACE_COLLECTION,
            detection_id,
            payload,
            context,
            models=self._models,
        )

    async def patch_batch(
        self, commands: Sequence[FacePatchBatchItem], context: GenericActor
    ) -> list[FaceResponse | None]:
        return await _patch_annotations(
            self._client, FACE_COLLECTION, commands, context, models=self._models
        )

    async def delete(self, detection_id: uuid.UUID, *, context: GenericActor) -> bool:
        return bool(
            await _delete_annotations(
                self._client, FACE_COLLECTION, [detection_id], context
            )
        )

    async def delete_batch(
        self, detection_ids: Sequence[uuid.UUID], *, context: GenericActor
    ) -> int:
        return await _delete_annotations(
            self._client, FACE_COLLECTION, detection_ids, context
        )

    async def search(self, query: SearchFacesRequest) -> SearchFacesResultListResponse:
        _require_default_sort(query)
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
        _require_default_sort(query)
        _require_postgres_for_evidence(query.filter_)
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
        if not is_missing(query.filter_) and not is_missing(
            query.filter_.entity_link_state
        ):
            fs.append(
                _property(
                    "entity_link_state",
                    [state.value for state in query.filter_.entity_link_state],
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
        await _require(self._client, SOURCE_COLLECTION, payload.source_id, "source")
        await _require(self._client, ENTITY_COLLECTION, payload.entity_id, "entity")
        i = new_uuid6()
        await self._client.collections.get(TEXT_MENTION_COLLECTION).data.insert(
            uuid=i,
            properties={
                "context": payload.context,
                **_link_properties(
                    (payload.entity_id, create_link_state(payload), None, None)
                ),
                "annotation_source_id": str(payload.source_id),
                **_props(payload, {"source_id", "entity_id"}),
            },
            references={"source": payload.source_id, "entity": payload.entity_id},
        )
        await _touch(self._client, [payload.entity_id], context)
        return TextMentionResponse.model_validate(
            {
                **payload.model_dump(),
                "entity_link_state": create_link_state(payload),
                "mention_id": i,
            }
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
        return await _patch_annotation(
            self._client, TEXT_MENTION_COLLECTION, mention_id, payload, context
        )

    async def patch_batch(
        self, commands: Sequence[TextMentionPatchBatchItem], context: GenericActor
    ) -> list[TextMentionResponse | None]:
        return await _patch_annotations(
            self._client, TEXT_MENTION_COLLECTION, commands, context
        )

    async def delete(self, mention_id: uuid.UUID, *, context: GenericActor) -> bool:
        return bool(
            await _delete_annotations(
                self._client, TEXT_MENTION_COLLECTION, [mention_id], context
            )
        )

    async def delete_batch(
        self, mention_ids: Sequence[uuid.UUID], *, context: GenericActor
    ) -> int:
        return await _delete_annotations(
            self._client, TEXT_MENTION_COLLECTION, mention_ids, context
        )


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
        for name in (FACE_COLLECTION, TEXT_MENTION_COLLECTION):
            matches = await self._client.collections.get(name).query.fetch_objects(
                filters=Filter.by_property("entity_link_verified_by_user_id").equal(
                    user_id
                ),
                limit=1,
            )
            if matches.objects:
                raise ValueError("cannot delete a link verifier")
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
    filters = []
    if n == FACE_COLLECTION:
        filters = WeaviateFaceRepository(client).filters(q.filter_)
    elif n == ENTITY_COLLECTION and q.filter_ is not None:
        f = q.filter_
        _require_postgres_for_evidence(f, allow_document_scope=True)
        filters = _direct(
            f,
            {
                "entity_type": "entity_type",
                "wikidata_id": "wikidata_id",
                "nlcr_authority_id": "nlcr_authority_id",
            },
        )
        if not is_missing(f.entity_id):
            filters.append(Filter.by_id().contains_any(f.entity_id))
        if any(
            not is_missing(getattr(f, field))
            for field in (
                "entity_link_state",
                "source_id",
                "document_source_id",
                "detection_id",
                "mention_id",
            )
        ):
            ids = await _evidence_ids(client, f, entities=True)
            filters.append(Filter.by_id().contains_any(list(ids) or [uuid.UUID(int=0)]))
    if n == ENTITY_COLLECTION:
        filters.extend(await _presence_filters(client, q.filter_, entities=True))
    scores: dict[uuid.UUID, float] = {}
    objects: dict[uuid.UUID, _StoredObject] = {}
    if not is_missing(q.query.text):
        for text in q.query.text:
            r = await client.collections.get(n).query.bm25(
                query=text,
                filters=_all(filters),
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
    fp = _fingerprint(q)
    after = _decode(q.cursor, fp)
    if after is not None:
        positions = [
            index
            for index, item in enumerate(items)
            if getattr(item, id_field) == after
        ]
        if not positions:
            raise ValueError("cursor is not valid for this query")
        start = positions[0] + 1
    else:
        start = 0
    selected = items[start : start + q.limit]
    if n == ENTITY_COLLECTION:
        await _attach_stats(client, selected, entities=True)
    return response(
        items=selected,
        limit=q.limit,
        total_count=len(items) if q.return_total_count else None,
        cursor=_encode(getattr(selected[-1], id_field), fp)
        if selected and start + q.limit < len(items)
        else None,
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
