"""Shared source scope and latest-modification criteria across resources (#52).

The matrix deliberately gives records and their linked annotations different
latest actors, reuses one archive document ID in two libraries and keeps an
unannotated document/page, so a filter cannot pass by reading the wrong record.
"""

import os
import uuid
from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.engine import make_url

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListFilter,
    EntityListRequest,
    EntityPatchRequest,
)
from people_gator_api.schemas.enums import EntityLinkState, EntityType, FaceKeypointType
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceCreateRequest,
    FaceListFilter,
    FaceListRequest,
    FacePatchRequest,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListFilter,
    TextMentionListRequest,
)
from people_gator_api.schemas.search import QueryBase, SearchDocumentsRequest, SearchEntitiesRequest
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListFilter,
    DocumentListRequest,
    PageCreateRequest,
    PageListFilter,
    PageListRequest,
)
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext
from people_gator_api.services.database_service import (
    create_postgres_schema,
    make_postgres_engine,
    make_postgres_session_factory,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not os.getenv("PEOPLE_GATOR_POSTGRES_TEST_URL"),
        reason="requires isolated PostgreSQL",
    ),
]


def _face(source_id, entity_id=None, **values):
    return FaceCreateRequest(
        identifier=uuid.uuid4().hex,
        bounding_box=BoundingBox(x=1, y=1, width=10, height=10),
        keypoints=[Keypoint(type=t, x=2, y=2) for t in FaceKeypointType],
        confidence=0.9,
        source_id=source_id,
        **({"entity_id": entity_id} if entity_id else {}),
        **values,
    )


@pytest_asyncio.fixture
async def matrix():
    engine = make_postgres_engine(make_url(os.environ["PEOPLE_GATOR_POSTGRES_TEST_URL"]))
    await create_postgres_schema(engine)
    sessions = make_postgres_session_factory(engine)
    async with sessions() as session:
        db = postgres_database(session)
        tag = uuid.uuid4().hex[:10]

        async def actor(name, key=False):
            user = await db.users.get_or_create(UserCreateRequest(
                display_name=name, is_active=True,
                external_subject=f"{name}-{tag}", external_issuer="issue52-tests",
            ))
            api_key = await db.api_keys.get_or_create(APIKeyCreateRequest(
                identifier=f"{name}-{tag}", display_name=name, user_id=user.user_id,
            )) if key else None
            return AuthContext(
                user_id=user.user_id, user=user,
                api_key_id=api_key.api_key_id if api_key else None,
                authentication_method="api_key" if api_key else "bearer", scopes=set(),
            )

        u_key = await actor("u", key=True)
        u = AuthContext(user_id=u_key.user_id, user=u_key.user, api_key_id=None,
                        authentication_method="bearer", scopes=set())
        v = await actor("v")
        l1, l2 = f"lib-a-{tag}", f"lib-b-{tag}"
        archive, quiet = uuid.uuid4(), uuid.uuid4()
        d1, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library=l1, document_id=archive))
        # The same archive document UUID in another library must never leak.
        d2, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library=l2, document_id=archive))
        d3, _ = await db.sources.get_or_create_document(DocumentCreateRequest(library=l1, document_id=quiet))

        async def page(library, document_id):
            created, _ = await db.sources.get_or_create_page(PageCreateRequest(
                library=library, document_id=document_id, page_id=uuid.uuid4(),
            ))
            return created

        p1a, p1b = await page(l1, archive), await page(l1, archive)
        p2a = await page(l2, archive)
        p3 = await page(l1, quiet)  # unannotated
        e1, e2, e3 = await db.entities.create_batch([
            EntityCreateRequest(entity_type=EntityType.person, name=f"Matrix {n} {tag}")
            for n in ("one", "two", "three")
        ], v)
        # F1: V's face linked to E1; E1 itself is later changed by U.
        f1 = await db.faces.create(_face(p1a.source_id, e1.entity_id), v)
        # F2: U's unassigned face, superseded by V. P1b/D1 latest change becomes V.
        f2 = await db.faces.create(_face(p1b.source_id), u_key)
        f2 = await db.faces.patch(f2.detection_id, FacePatchRequest(entity_id=e3.entity_id), v)
        f2 = await db.faces.patch(f2.detection_id, FacePatchRequest(entity_id=None), v)
        # E3 has a manual face in L1 and an automatic mention in L2.
        f3 = await db.faces.create(_face(
            p1a.source_id, e3.entity_id, entity_link_state=EntityLinkState.manual,
        ), v)
        m2 = await db.text_mentions.create(TextMentionCreateRequest(
            name="Three", entity_id=e3.entity_id, source_id=p2a.source_id,
        ), v)
        # M1: U's key links E2 in the other library and is P2a/D2's latest change.
        m1 = await db.text_mentions.create(TextMentionCreateRequest(
            name="Two", entity_id=e2.entity_id, source_id=p2a.source_id,
        ), u_key)
        e1 = await db.entities.patch(e1.entity_id, EntityPatchRequest(short_description="edited"), u)
        yield SimpleNamespace(
            db=db, u=u, u_key=u_key, v=v, l1=l1, l2=l2,
            d1=d1, d2=d2, d3=d3, p1a=p1a, p1b=p1b, p2a=p2a, p3=p3,
            e1=e1, e2=e2, e3=e3, f1=f1, f2=f2, f3=f3, m1=m1, m2=m2,
        )
    await engine.dispose()


async def entity_ids(m, **values):
    result = await m.db.entities.list(EntityListRequest(
        limit=100, filter_=EntityListFilter(**{"library": [m.l1, m.l2], **values}),
    ))
    return {item.entity_id for item in result.items}


async def document_ids(m, **values):
    result = await m.db.sources.list_documents(DocumentListRequest(
        limit=100, filter_=DocumentListFilter(**{"library": [m.l1, m.l2], **values}),
    ))
    return {item.source_id for item in result.items}


async def page_ids(m, **values):
    result = await m.db.sources.list_pages(PageListRequest(
        limit=100, filter_=PageListFilter(**{"library": [m.l1, m.l2], **values}),
    ))
    return {item.source_id for item in result.items}


async def face_ids(m, **values):
    result = await m.db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(**{"library": [m.l1, m.l2], **values}),
    ))
    return {item.detection_id for item in result.items}


async def mention_ids(m, **values):
    result = await m.db.text_mentions.list(TextMentionListRequest(
        limit=100, filter_=TextMentionListFilter(**{"library": [m.l1, m.l2], **values}),
    ))
    return {item.mention_id for item in result.items}


async def test_same_user_selection_finds_each_resources_own_latest_change(matrix):
    m = matrix
    by_u = {"last_touched_by_user_id": [m.u.user_id]}
    # Documents: D1's U change was superseded by V; D3 has no recorded change.
    assert await document_ids(m, **by_u) == {m.d2.source_id}
    assert await page_ids(m, **by_u) == {m.p2a.source_id}
    # People: E1 is U's own edit although its linked face is V's.
    assert await entity_ids(m, **by_u) == {m.e1.entity_id, m.e2.entity_id}
    # Faces/mentions: the record itself, not its linked person or source.
    assert await face_ids(m, **by_u) == set()
    assert await mention_ids(m, **by_u) == {m.m1.mention_id}
    assert await face_ids(m, last_touched_by_user_id=[m.v.user_id]) == {
        m.f1.detection_id, m.f2.detection_id, m.f3.detection_id,
    }
    # Superseded editors and creation/ownership never match.
    assert await entity_ids(m, last_touched_by_user_id=[m.v.user_id]) == {m.e3.entity_id}
    assert await document_ids(m, last_touched_by_user_id=[m.v.user_id]) == {m.d1.source_id}


async def test_api_key_and_inclusive_timezone_aware_ranges(matrix):
    m = matrix
    key = {"last_touched_by_api_key_id": [m.u_key.api_key_id]}
    # E1's later bearer edit cleared the key; E2's key change remains latest.
    assert await entity_ids(m, **key) == {m.e2.entity_id}
    assert await document_ids(m, **key) == {m.d2.source_id}
    assert await mention_ids(m, **key) == {m.m1.mention_id}
    assert await face_ids(m, **key) == set()
    at = m.e1.last_touched_at
    local = at.astimezone(timezone(timedelta(hours=2)))
    assert await entity_ids(m, last_touched_from=local, last_touched_to=local) == {m.e1.entity_id}
    assert await entity_ids(m, last_touched_from=at + timedelta(microseconds=1)) == set()
    # Unknown history is excluded by any bound rather than treated as a match.
    early = at - timedelta(days=3650)
    assert m.d3.source_id not in await document_ids(m, last_touched_from=early)
    assert m.d3.source_id in await document_ids(m)


async def test_source_scope_uses_real_relationships_without_leaks(matrix):
    m = matrix
    # Plain source browsing keeps unannotated documents and pages.
    assert await document_ids(m, library=[m.l1]) == {m.d1.source_id, m.d3.source_id}
    assert await page_ids(m, library=[m.l1]) == {m.p1a.source_id, m.p1b.source_id, m.p3.source_id}
    # A document scope includes its registered pages, never the same archive ID elsewhere.
    assert await page_ids(m, document_source_id=[m.d1.source_id]) == {m.p1a.source_id, m.p1b.source_id}
    assert await document_ids(m, document_source_id=[m.d1.source_id]) == {m.d1.source_id}
    assert await entity_ids(m, document_source_id=[m.d1.source_id]) == {m.e1.entity_id, m.e3.entity_id}
    assert await entity_ids(m, document_source_id=[m.d2.source_id]) == {m.e2.entity_id, m.e3.entity_id}
    # A page scope selects the containing document and the page's linked records.
    assert await document_ids(m, page_source_id=[m.p2a.source_id]) == {m.d2.source_id}
    assert await page_ids(m, page_source_id=[m.p3.source_id]) == {m.p3.source_id}
    assert await entity_ids(m, page_source_id=[m.p1b.source_id]) == set()
    assert await face_ids(m, page_source_id=[m.p1b.source_id]) == {m.f2.detection_id}
    assert await mention_ids(m, document_source_id=[m.d1.source_id]) == set()
    # Unknown identifiers select nothing; they never mean "unassigned".
    assert await entity_ids(m, document_source_id=[uuid.uuid4()]) == set()


async def test_relationship_predicates_need_one_matching_annotation(matrix):
    m = matrix
    # E3 has a link in L1 and a link on P2a (L2), but no single link in both.
    assert await entity_ids(m, library=[m.l1], page_source_id=[m.p2a.source_id]) == set()
    # Its manual link is in L1 and its automatic link in L2.
    automatic = [EntityLinkState.automatic]
    result = await m.db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        library=[m.l1], entity_link_state=automatic,
    )))
    assert {item.entity_id for item in result.items} == {m.e1.entity_id}
    result = await m.db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        library=[m.l2], entity_link_state=automatic,
    )))
    assert {item.entity_id for item in result.items} == {m.e2.entity_id, m.e3.entity_id}
    # Documents: link state is evaluated inside the selected page scope.
    assert await document_ids(m, page_source_id=[m.p1b.source_id], entity_link_state=[EntityLinkState.manual]) == set()
    assert await document_ids(m, page_source_id=[m.p1a.source_id], entity_link_state=[EntityLinkState.manual]) == {m.d1.source_id}
    # An unassigned face elsewhere in the document cannot satisfy a selected page.
    assert await document_ids(m, page_source_id=[m.p1a.source_id], has_unassigned_faces=True) == set()
    assert await document_ids(m, page_source_id=[m.p1b.source_id], has_unassigned_faces=True) == {m.d1.source_id}
    assert await document_ids(m, page_source_id=[m.p1a.source_id], has_unassigned_faces=False) == {m.d1.source_id}
    # Different fields AND; values within one field OR.
    assert await entity_ids(m, last_touched_by_user_id=[m.u.user_id, m.v.user_id],
                            document_source_id=[m.d2.source_id]) == {m.e2.entity_id, m.e3.entity_id}


async def test_counts_and_cursors_apply_every_shared_criterion(matrix):
    m = matrix
    shared = EntityListFilter(library=[m.l1, m.l2], last_touched_by_user_id=[m.u.user_id])
    seen, cursor = [], None
    while True:
        page = await m.db.entities.list(EntityListRequest(
            limit=1, cursor=cursor, return_total_count=True, filter_=shared,
        ))
        assert page.total_count == 2
        seen.extend(item.entity_id for item in page.items)
        cursor = page.cursor
        if cursor is None:
            break
    assert sorted(seen) == sorted([m.e1.entity_id, m.e2.entity_id])
    # A cursor is bound to its criteria; changing them must restart pagination.
    first = await m.db.entities.list(EntityListRequest(limit=1, filter_=shared))
    changed = shared.model_copy(update={"last_touched_by_user_id": [m.v.user_id]})
    with pytest.raises(ValueError):
        await m.db.entities.list(EntityListRequest(limit=1, cursor=first.cursor, filter_=changed))
    # Searches use the same criteria before ranking/counting.
    found = await m.db.entities.search(SearchEntitiesRequest(
        limit=10, return_total_count=True, query=QueryBase(text=["Matrix"]), filter_=shared,
    ))
    assert {item.entity_id for item in found.items} == {m.e1.entity_id, m.e2.entity_id}
    docs = await m.db.sources.search_documents(SearchDocumentsRequest(
        limit=10, return_total_count=True, query=QueryBase(text=[str(m.d1.document_id)]),
        filter_=DocumentListFilter(library=[m.l1, m.l2], last_touched_by_user_id=[m.u.user_id]),
    ))
    assert {item.source_id for item in docs.items} == {m.d2.source_id}
    assert docs.total_count == 1
