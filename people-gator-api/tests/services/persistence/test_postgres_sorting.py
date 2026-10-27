"""Issue #33: allowlisted sorting precedes pagination on the complete result set."""

import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListFilter,
    EntityListRequest,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.search import QueryBase, SearchEntitiesRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext

pytestmark = pytest.mark.asyncio

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def text_key(value: str) -> tuple[str, str]:
    stripped = "".join(
        char for char in unicodedata.normalize("NFD", value) if not unicodedata.combining(char)
    )
    return stripped.lower(), value


async def pages(fetch, request_type, limit=2, **kwargs):
    """Follow every cursor; return all items and assert totals stay unchanged."""
    items, cursor, totals = [], None, set()
    while True:
        page = await fetch(request_type(limit=limit, cursor=cursor, return_total_count=True, **kwargs))
        items.extend(page.items)
        totals.add(page.total_count)
        cursor = page.cursor
        if cursor is None:
            break
    assert len(totals) == 1
    return items, totals.pop()


@pytest_asyncio.fixture
async def sorted_records(migrated_postgres):
    sessions = async_sessionmaker(migrated_postgres, expire_on_commit=False)
    async with sessions() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(
            display_name="Sorter", is_active=True,
            external_subject=uuid.uuid4().hex, external_issuer="issue33",
        ))
        key = await db.api_keys.get_or_create(APIKeyCreateRequest(
            identifier="issue33-" + uuid.uuid4().hex, display_name="Sort key", user_id=user.user_id,
        ))
        actor = AuthContext(user_id=user.user_id, api_key_id=key.api_key_id,
                            authentication_method="api_key", scopes=set())
        names = ["Émil Zorn", "ada Novak", "Ada Novak", "ADA NOVAK", "Bea Ortiz", "Ada Novak"]
        entities = await db.entities.create_batch(
            [EntityCreateRequest(entity_type=EntityType.person, name=name) for name in names], actor,
        )
        # Ties, a missing (historical) edit time, and distinct times.
        times = [T0, T0 + timedelta(days=2), T0 + timedelta(days=2), None, T0 + timedelta(days=1), T0]
        for entity, touched in zip(entities, times, strict=True):
            await session.execute(
                text("UPDATE pg_demo_entities SET last_touched_at = :at WHERE id = :id"),
                {"at": touched, "id": entity.entity_id},
            )
        await session.commit()
        yield SimpleNamespace(db=db, session=session, actor=actor, entities=entities,
                              ids=[item.entity_id for item in entities], times=dict(zip(
                                  [item.entity_id for item in entities], times, strict=True)))


async def test_entity_name_sort_is_collated_tied_and_paged(sorted_records):
    r = sorted_records
    scope = EntityListFilter(entity_id=r.ids)
    for direction in ("asc", "desc"):
        items, total = await pages(r.db.entities.list, EntityListRequest, filter_=scope,
                                   sort="name", sort_direction=direction)
        assert total == len(r.ids)
        assert len({item.entity_id for item in items}) == len(r.ids)
        expected = sorted(r.entities, key=lambda item: (text_key(item.name), item.entity_id.int))
        if direction == "desc":
            expected = sorted(r.entities, key=lambda item: item.entity_id.int)
            expected = sorted(expected, key=lambda item: text_key(item.name), reverse=True)
        assert [item.entity_id for item in items] == [item.entity_id for item in expected]
    # Distinct spellings stay distinct; equal names tie-break by identity.
    names = [item.name for item in items]
    assert names.index("Émil Zorn") == 0


async def test_entity_time_sort_places_unknown_last_in_both_directions(sorted_records):
    r = sorted_records
    scope = EntityListFilter(entity_id=r.ids)
    for direction in ("asc", "desc"):
        items, _ = await pages(r.db.entities.list, EntityListRequest, filter_=scope,
                               sort="last_touched_at", sort_direction=direction)
        known = [item for item in r.ids if r.times[item] is not None]
        ordered = sorted(known, key=lambda item: item.int)
        ordered = sorted(ordered, key=lambda item: r.times[item], reverse=direction == "desc")
        assert [item.entity_id for item in items] == [*ordered, *[i for i in r.ids if r.times[i] is None]]


async def test_identity_sort_and_default_order(sorted_records):
    r = sorted_records
    scope = EntityListFilter(entity_id=r.ids)
    default, _ = await pages(r.db.entities.list, EntityListRequest, filter_=scope)
    assert [item.entity_id for item in default] == sorted(r.ids, key=lambda item: item.int)
    descending, _ = await pages(r.db.entities.list, EntityListRequest, filter_=scope,
                                sort="entity_id", sort_direction="desc")
    assert [item.entity_id for item in descending] == sorted(r.ids, key=lambda item: -item.int)


async def test_cursor_is_bound_to_the_effective_sort(sorted_records):
    r = sorted_records
    scope = EntityListFilter(entity_id=r.ids)
    first = await r.db.entities.list(EntityListRequest(filter_=scope, limit=2, sort="name"))
    assert first.cursor
    for changed in ({"sort": "name", "sort_direction": "desc"}, {"sort": "created_at"}, {}):
        with pytest.raises(ValueError, match="different query"):
            await r.db.entities.list(EntityListRequest(filter_=scope, limit=2, cursor=first.cursor, **changed))


async def test_search_sorts_complete_candidate_set_before_paging(sorted_records):
    r = sorted_records
    scope = EntityListFilter(entity_id=r.ids)
    query = QueryBase(text=["Novak"])
    relevance, total = await pages(r.db.entities.search, SearchEntitiesRequest, query=query, filter_=scope)
    by_name, by_name_total = await pages(r.db.entities.search, SearchEntitiesRequest, query=query,
                                         filter_=scope, sort="name", sort_direction="desc")
    assert total == by_name_total
    assert {item.entity_id for item in relevance} == {item.entity_id for item in by_name}
    expected = sorted(by_name, key=lambda item: item.entity_id.int)
    expected = sorted(expected, key=lambda item: text_key(item.name), reverse=True)
    assert [item.entity_id for item in by_name] == [item.entity_id for item in expected]
    ascending, _ = await pages(r.db.entities.search, SearchEntitiesRequest, query=query,
                               filter_=scope, sort="relevance", sort_direction="asc")
    assert [(item.score, item.entity_id.int) for item in ascending] == sorted(
        (item.score, item.entity_id.int) for item in relevance)


from people_gator_api.schemas.enums import FaceKeypointType  # noqa: E402
from people_gator_api.schemas.faces import (  # noqa: E402
    BoundingBox,
    FaceCreateRequest,
    FaceListFilter,
    FaceListRequest,
    FacePatchBatchItem,
    Keypoint,
)
from people_gator_api.schemas.mentions import (  # noqa: E402
    TextMentionCreateRequest,
    TextMentionGroupListRequest,
    TextMentionListFilter,
    TextMentionListRequest,
)
from people_gator_api.schemas.sources import (  # noqa: E402
    DocumentCreateRequest,
    DocumentListFilter,
    DocumentListRequest,
    PageCreateRequest,
    PageListFilter,
    PageListRequest,
)

STATE_ORDER = {"verified": 0, "manual": 1, "automatic": 2, None: 3}


def face_payload(source_id, confidence, entity_id=None, state=None):
    extra = {"entity_id": entity_id, "entity_link_state": state} if entity_id else {}
    return FaceCreateRequest(
        source_id=source_id, confidence=confidence,
        bounding_box=BoundingBox(x=0, y=0, width=50, height=50),
        keypoints=[Keypoint(type=kind, x=10 + i, y=10 + i) for i, kind in enumerate(FaceKeypointType)],
        **extra,
    )


@pytest_asyncio.fixture
async def collection(sorted_records):
    """Two libraries, unnamed and accent-named documents, uneven page counts."""
    r = sorted_records
    marker = uuid.uuid4().hex[:8]
    libraries = [f"zeta-{marker}", f"Alpha-{marker}"]
    documents, pages_by_doc = [], {}
    for library, name, page_count in [
        (libraries[0], "Ödön album", 1),
        (libraries[1], "odon album", 3),
        (libraries[1], None, 0),
        (libraries[0], "Bravo", 3),
    ]:
        document, _ = await r.db.sources.get_or_create_document(
            DocumentCreateRequest(library=library, document_id=uuid.uuid4(), name=name))
        documents.append(document)
        pages_by_doc[document.source_id] = []
        for _ in range(page_count):
            page, _ = await r.db.sources.get_or_create_page(PageCreateRequest(
                library=library, document_id=document.document_id, page_id=uuid.uuid4()))
            pages_by_doc[document.source_id].append(page)
    pages = [page for items in pages_by_doc.values() for page in items]
    person = r.entities[0].entity_id
    faces = await r.db.faces.create_batch([
        face_payload(pages[0].source_id, 0.5, person, "manual"),
        face_payload(pages[1].source_id, 0.9, person, "automatic"),
        face_payload(pages[2].source_id, 0.5),
        face_payload(pages[3].source_id, 0.7, person, "manual"),
        face_payload(pages[4].source_id, 0.9, person, "automatic"),
    ], r.actor)
    await r.db.faces.patch_batch([FacePatchBatchItem(detection_id=faces[3].detection_id,
                                                     entity_link_state="verified")], r.actor)
    mentions = await r.db.text_mentions.create_batch([
        TextMentionCreateRequest(name=name, entity_id=person, source_id=pages[index % len(pages)].source_id)
        for index, name in enumerate(
            ["Ada Novak", "A. Novak", "ADA NOVAK", "Ada Novak", "ada novak", "Ada Novak", "A. Novak"])
    ], r.actor)
    yield SimpleNamespace(r=r, libraries=libraries, documents=documents, pages=pages,
                          pages_by_doc=pages_by_doc, faces=faces, mentions=mentions, person=person)


async def test_document_sorts_cover_name_library_and_page_count(collection):
    c = collection
    scope = DocumentListFilter(library=c.libraries)
    by_count, total = await pages(c.r.db.sources.list_documents, DocumentListRequest, filter_=scope,
                                  sort="page_count")
    assert total == 4
    counts = [len(c.pages_by_doc[item.source_id]) for item in by_count]
    assert counts == sorted(counts, reverse=True)
    tied = [item.source_id for item in by_count if len(c.pages_by_doc[item.source_id]) == 3]
    assert tied == sorted(tied, key=lambda item: item.int)

    by_name, _ = await pages(c.r.db.sources.list_documents, DocumentListRequest, filter_=scope,
                             sort="name", sort_direction="desc")
    names = [item.name for item in by_name]
    # Unknown names compare as empty strings and follow named rows descending.
    assert names == ["Ödön album", "odon album", "Bravo", None]

    by_library, _ = await pages(c.r.db.sources.list_documents, DocumentListRequest, filter_=scope,
                                sort="library")
    assert [item.library for item in by_library] == [c.libraries[1]] * 2 + [c.libraries[0]] * 2
    assert [item.document_id.int for item in by_library[:2]] == sorted(
        item.document_id.int for item in by_library[:2])


async def test_page_identifier_sorts_never_invent_page_numbers(collection):
    c = collection
    scope = PageListFilter(library=c.libraries)
    by_library, total = await pages(c.r.db.sources.list_pages, PageListRequest, filter_=scope,
                                    sort="library", limit=3)
    assert total == len(c.pages)
    assert [(item.library.lower(), item.document_id.int, item.page_id.int) for item in by_library] == sorted(
        (item.library.lower(), item.document_id.int, item.page_id.int) for item in c.pages)
    by_page, _ = await pages(c.r.db.sources.list_pages, PageListRequest, filter_=scope,
                             sort="page_id", sort_direction="desc")
    assert [item.page_id for item in by_page] == sorted((p.page_id for p in c.pages), key=lambda i: -i.int)


async def test_face_sorts_by_state_confidence_and_source(collection):
    c = collection
    scope = FaceListFilter(source_id=[page.source_id for page in c.pages])
    by_state, total = await pages(c.r.db.faces.list, FaceListRequest, filter_=scope, sort="link_state")
    assert total == 5
    states = [item.entity_link_state.value if item.entity_link_state else None for item in by_state]
    assert states == sorted(states, key=lambda state: STATE_ORDER[state])
    by_state_desc, _ = await pages(c.r.db.faces.list, FaceListRequest, filter_=scope,
                                   sort="link_state", sort_direction="desc")
    # Unassigned is unknown and stays last in both directions.
    assert by_state_desc[-1].entity_link_state is None
    assert by_state_desc[0].entity_link_state.value == "automatic"

    by_confidence, _ = await pages(c.r.db.faces.list, FaceListRequest, filter_=scope, sort="confidence")
    assert [(item.confidence, item.detection_id.int) for item in by_confidence] == sorted(
        (item.confidence, item.detection_id.int) for item in c.faces)

    by_source, _ = await pages(c.r.db.faces.list, FaceListRequest, filter_=scope, sort="source")
    page_of = {page.source_id: page for page in c.pages}
    keys = [(page_of[f.source_id].library.lower(), page_of[f.source_id].document_id.int,
             page_of[f.source_id].page_id.int) for f in by_source]
    assert keys == sorted(keys)


async def test_mention_flat_and_exact_appearance_groups(collection):
    c = collection
    scope = TextMentionListFilter(entity_id=[c.person])
    groups, total = await pages(c.r.db.text_mentions.list_groups, TextMentionGroupListRequest,
                                filter_=scope, limit=2)
    assert total == 4
    assert [(group.name, group.occurrence_count) for group in groups] == [
        ("A. Novak", 2), ("ADA NOVAK", 1), ("Ada Novak", 3), ("ada novak", 1)]
    by_count, _ = await pages(c.r.db.text_mentions.list_groups, TextMentionGroupListRequest,
                              filter_=scope, sort="count", limit=1)
    assert [group.occurrence_count for group in by_count] == [3, 2, 1, 1]
    assert [group.name for group in by_count[2:]] == ["ADA NOVAK", "ada novak"]

    occurrences, occurrence_total = await pages(
        c.r.db.text_mentions.list, TextMentionListRequest,
        filter_=TextMentionListFilter(entity_id=[c.person], name=["Ada Novak"]), sort="source")
    assert occurrence_total == 3 and {item.name for item in occurrences} == {"Ada Novak"}

    flat, _ = await pages(c.r.db.text_mentions.list, TextMentionListRequest, filter_=scope,
                          sort="text", sort_direction="desc", limit=3)
    assert [item.name for item in flat] == [
        "ada novak", "Ada Novak", "Ada Novak", "Ada Novak", "ADA NOVAK", "A. Novak", "A. Novak"]


async def test_source_sorts_require_a_resource_type(collection):
    from people_gator_api.schemas.sources import GenericSourceListRequest

    with pytest.raises(ValueError, match="page or document"):
        await collection.r.db.sources.list(GenericSourceListRequest(limit=1, sort="library"))


async def test_page_search_sorts_bounded_candidates_before_paging(collection):
    from people_gator_api.schemas.search import SearchPagesRequest

    c = collection
    query = QueryBase(text=[c.libraries[1]])
    scope = PageListFilter(library=c.libraries)
    relevance, total = await pages(c.r.db.sources.search_pages, SearchPagesRequest, query=query, filter_=scope)
    by_page, sorted_total = await pages(c.r.db.sources.search_pages, SearchPagesRequest, query=query,
                                        filter_=scope, sort="page_id", sort_direction="desc", limit=1)
    assert total == sorted_total == 3
    assert {item.source_id for item in relevance} == {item.source_id for item in by_page}
    assert [item.page_id.int for item in by_page] == sorted((item.page_id.int for item in by_page), reverse=True)


async def test_ranked_candidates_removed_after_scoring_are_dropped():
    from people_gator_api.persistence.postgres.sorting import SortKey, SortSpec, sort_ranked
    from people_gator_api.schemas.sorting import SortDirection

    kept, removed = uuid.uuid4(), uuid.uuid4()
    spec = SortSpec("name:asc", (SortKey(text("1"), "text"),))
    ranked = [(removed, 0.9, None, None), (kept, 0.5, None, None)]
    assert sort_ranked(ranked, spec, SortDirection.ASC, {kept: ("ada",)}) == [(kept, 0.5, None, None)]


@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_unknown_document_names_agree_in_paged_browse_and_search(collection, direction):
    from people_gator_api.schemas.search import SearchDocumentsRequest

    c = collection
    # Multiple unknown names must keep the same UUID tie order in both
    # directions, even when a cursor splits the unknown-name group.
    unknown, _ = await c.r.db.sources.get_or_create_document(DocumentCreateRequest(
        library=c.libraries[0], document_id=uuid.uuid4(), name=None,
    ))
    documents = [*c.documents, unknown]
    scope = DocumentListFilter(library=c.libraries)
    expected = sorted(documents, key=lambda row: row.source_id.int)
    expected.sort(key=lambda row: text_key(row.name or ""), reverse=direction == "desc")
    browse, total = await pages(c.r.db.sources.list_documents, DocumentListRequest,
                               filter_=scope, sort="name", sort_direction=direction, limit=1)
    search, search_total = await pages(c.r.db.sources.search_documents, SearchDocumentsRequest,
                                      query=QueryBase(text=c.libraries), filter_=scope,
                                      sort="name", sort_direction=direction, limit=1)
    assert total == search_total == len(expected)
    ids = [row.source_id for row in expected]
    assert [row.source_id for row in browse] == ids
    assert [row.source_id for row in search] == ids
    assert len(set(ids)) == len(ids)
    unknowns = [row for row in browse if row.name is None]
    edge = browse[:2] if direction == "asc" else browse[-2:]
    assert [row.source_id for row in edge] == sorted(row.source_id for row in unknowns)
    assert len(unknowns) == 2


@pytest.mark.parametrize("mode,expected", [("document", 3), ("page", 7)])
async def test_mention_source_groups_cover_all_pages_with_stable_identity(collection, mode, expected):
    c = collection
    groups, total = await pages(c.r.db.text_mentions.list_groups, TextMentionGroupListRequest,
                               filter_=TextMentionListFilter(entity_id=[c.person]),
                               group_by=mode, limit=1)
    assert total == expected
    assert len({g.source_id for g in groups}) == expected
    assert sum(g.occurrence_count for g in groups) == len(c.mentions)
    for group in groups:
        scope = ({"document_source_id": [group.source_id]} if mode == "document"
                 else {"source_id": [group.source_id]})
        occurrences, count = await pages(c.r.db.text_mentions.list, TextMentionListRequest,
                                        filter_=TextMentionListFilter(entity_id=[c.person], **scope))
        assert count == group.occurrence_count
        assert all(m.source_id in {p.source_id for p in c.pages} for m in occurrences)
    filtered, _ = await pages(c.r.db.text_mentions.list_groups, TextMentionGroupListRequest,
                             group_by=mode, filter_=TextMentionListFilter(
                                 entity_id=[c.person], source_id=[c.pages[0].source_id]))
    assert len(filtered) == 1 and filtered[0].occurrence_count == 1
