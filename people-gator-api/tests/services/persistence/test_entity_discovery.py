"""Synthetic regressions for discovery's numerical and entity reference contracts."""

import math
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.faces import (
    BoundingBox,
    FaceCreateRequest,
    FaceEmbedding,
    Keypoint,
)
from people_gator_api.schemas.enums import FaceKeypointType
from people_gator_api.schemas.search import (
    EntityAnnotation,
    QueryBase,
    SearchEntitiesRequest,
    SearchFacesRequest,
)
from people_gator_api.schemas.sources import PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest

MODEL = "discovery-regression-2d"


@pytest.fixture
def isolated_discovery_indexes():
    from people_gator_api.persistence.postgres.models import (
        FaceEmbedding as EmbeddingRow,
    )

    # Model registration attaches dynamic indexes to process-wide metadata.
    # Keep private-schema tests from leaking definitions into bootstrap tests.
    table = EmbeddingRow.__table__
    original_indexes = set(table.indexes)
    yield
    table.indexes.difference_update(table.indexes - original_indexes)


@pytest_asyncio.fixture
async def discovery(migrated_postgres, isolated_discovery_indexes):
    async with async_sessionmaker(
        migrated_postgres, expire_on_commit=False
    )() as session:
        db = postgres_database(session)
        actor = await db.users.get_or_create(
            UserCreateRequest(
                display_name="Synthetic discovery",
                is_active=True,
                external_subject="discovery",
                external_issuer="test",
            )
        )
        await db.face_models.register(
            FaceModelRegisterRequest(model_stub=MODEL, embedding_dim=2)
        )
        page, _ = await db.sources.get_or_create_page(
            PageCreateRequest(
                library="synthetic",
                document_id=uuid.uuid4(),
                page_id=uuid.uuid4(),
            )
        )
        reference, candidate, empty = await db.entities.create_batch(
            [
                EntityCreateRequest(
                    entity_type="person",
                    name="Zephyr Cartographer",
                    aliases=["Saffron Navigator"],
                ),
                EntityCreateRequest(entity_type="person", name="Useful Portrait"),
                EntityCreateRequest(entity_type="person", name="Empty Signal"),
            ],
            actor,
        )

        async def face(key, vector, entity=reference):
            return await db.faces.create(
                FaceCreateRequest(
                    identifier=key,
                    bounding_box=BoundingBox(x=1, y=1, width=10, height=10),
                    confidence=0.9,
                    keypoints=[Keypoint(type=t, x=2, y=2) for t in FaceKeypointType],
                    source_id=page.source_id,
                    entity_id=entity.entity_id if entity else None,
                    embeddings=[FaceEmbedding(model_identifier=MODEL, vector=vector)]
                    if vector is not None
                    else [],
                ),
                actor,
            )

        refs = [await face(f"reference-{i}", [1.0, i / 100]) for i in range(12)]
        zero_reference = await face("zero-reference", [0.0, 0.0])
        missing_reference = await face("missing-reference", None)
        useful = await face("useful", [1.0, 0.0], candidate)
        zero_candidate = await face("zero-candidate", [0.0, 0.0], candidate)
        yield (
            db,
            reference,
            candidate,
            empty,
            refs,
            zero_reference,
            missing_reference,
            useful,
            zero_candidate,
            actor,
            page,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregation", ["min", "max", "average"])
@pytest.mark.parametrize("many", [False, True])
async def test_zero_candidate_does_not_poison_usable_results(
    discovery, aggregation, many
):
    db, _, candidate, _, refs, _, _, useful, zero_candidate, *_ = discovery
    query = QueryBase(
        face_id=[item.detection_id for item in (refs if many else refs[:1])],
        face_embedding_model=MODEL,
        score_aggregation=aggregation,
    )
    entities = await db.entities.search(SearchEntitiesRequest(query=query, limit=50))
    hit = next(item for item in entities.items if item.entity_id == candidate.entity_id)
    assert math.isfinite(hit.face_score) and hit.face_score > 0.99
    assert zero_candidate.detection_id not in hit.matched_detection_ids
    faces = await db.faces.search(SearchFacesRequest(query=query, limit=50))
    assert useful.detection_id in {item.detection_id for item in faces.items}
    assert zero_candidate.detection_id not in {
        item.detection_id for item in faces.items
    }
    assert all(math.isfinite(item.face_score) for item in faces.items)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["faces", "entities"])
async def test_explicit_unusable_reference_is_strict(discovery, endpoint):
    db, _, _, _, refs, zero, missing, *_ = discovery
    request_type = SearchFacesRequest if endpoint == "faces" else SearchEntitiesRequest
    repository = getattr(db, endpoint)
    for face, message in ((zero, "unusable cosine"), (missing, "lacks embedding")):
        with pytest.raises(ValueError, match=message):
            await repository.search(
                request_type(
                    limit=50,
                    query=QueryBase(
                        face_id=[refs[0].detection_id, face.detection_id],
                        face_embedding_model=MODEL,
                    ),
                )
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["faces", "entities"])
async def test_entity_annotations_match_only_the_selected_explicit_inputs(
    discovery, endpoint
):
    from itertools import combinations
    from people_gator_api.schemas.search import EntitySearchQuery

    db, reference, _, _, refs, _, _, _, _, actor, page = discovery
    # Text and appearance lead to separate stored candidates.
    names = await db.entities.create_batch(
        [
            EntityCreateRequest(entity_type="person", name=reference.name),
            EntityCreateRequest(entity_type="person", name=reference.aliases[0]),
        ],
        actor,
    )
    for entity in names:
        await db.faces.create(
            FaceCreateRequest(
                identifier=entity.name,
                bounding_box=BoundingBox(x=1, y=1, width=10, height=10),
                confidence=0.9,
                keypoints=[Keypoint(type=t, x=2, y=2) for t in FaceKeypointType],
                source_id=page.source_id,
                entity_id=entity.entity_id,
                embeddings=[FaceEmbedding(model_identifier=MODEL, vector=[0.0, 1.0])],
            ),
            actor,
        )
    request_type = SearchFacesRequest if endpoint == "faces" else SearchEntitiesRequest
    repository = getattr(db, endpoint)

    for size in (1, 2, 3):
        for selection in combinations(["faces", "aliases", "name"], size):
            actual = await repository.search(
                request_type(
                    limit=50,
                    query=EntitySearchQuery(
                        entity_id=reference.entity_id,
                        entity_annotations=list(selection),
                        face_embedding_model=MODEL,
                    ),
                )
            )
            explicit = QueryBase(
                **(
                    {
                        "text": ([reference.name] if "name" in selection else [])
                        + (reference.aliases if "aliases" in selection else [])
                    }
                    if "name" in selection or "aliases" in selection
                    else {}
                ),
                **(
                    {"face_id": [item.detection_id for item in refs]}
                    if "faces" in selection
                    else {}
                ),
                face_embedding_model=MODEL,
            )
            # Match entity self-exclusion using the public result filter.
            from people_gator_api.schemas.entities import EntityListFilter
            from people_gator_api.schemas.faces import FaceListFilter

            allowed = [item.entity_id for item in names]
            allowed += [discovery[2].entity_id, discovery[3].entity_id]
            filter_type = FaceListFilter if endpoint == "faces" else EntityListFilter
            expected = await repository.search(
                request_type(
                    limit=50, query=explicit, filter_=filter_type(entity_id=allowed)
                )
            )
            assert actual.items == expected.items
            if "faces" not in selection:
                assert all(item.face_score is None for item in actual.items)
            if "name" not in selection and "aliases" not in selection:
                assert all(item.text_score is None for item in actual.items)
            if selection == ("name",):
                assert actual.items[0].text_score == 1
            if selection == ("aliases",):
                assert actual.items[0].text_score == 1

    omitted = await repository.search(
        request_type(
            limit=50,
            query=EntitySearchQuery(
                entity_id=reference.entity_id,
                face_embedding_model=MODEL,
            ),
        )
    )
    assert omitted.items == actual.items


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["faces", "entities"])
async def test_entity_errors_filters_and_query_bound_cursors(discovery, endpoint):
    from people_gator_api.schemas.search import EntitySearchQuery
    from people_gator_api.schemas.entities import EntityListFilter
    from people_gator_api.schemas.faces import FaceListFilter

    db, reference, candidate, empty, *_ = discovery
    request_type = SearchFacesRequest if endpoint == "faces" else SearchEntitiesRequest
    repository = getattr(db, endpoint)
    for entity_id, selection, error in (
        (uuid.uuid4(), ["faces"], "does not exist"),
        (empty.entity_id, ["faces"], "no usable search signal"),
        (empty.entity_id, ["aliases"], "no usable search signal"),
    ):
        with pytest.raises(ValueError, match=error):
            await repository.search(
                request_type(
                    limit=50,
                    query=EntitySearchQuery(
                        entity_id=entity_id,
                        entity_annotations=selection,
                        face_embedding_model=MODEL,
                    ),
                )
            )
    # Explicit signals may supplement an empty entity selection.
    await repository.search(
        request_type(
            limit=50,
            query=EntitySearchQuery(
                entity_id=empty.entity_id,
                entity_annotations=["faces"],
                text=["Useful Portrait"],
                face_embedding_model=MODEL,
            ),
        )
    )
    query = EntitySearchQuery(
        entity_id=reference.entity_id,
        entity_annotations=["faces"],
        face_embedding_model=MODEL,
    )
    filter_type = FaceListFilter if endpoint == "faces" else EntityListFilter
    filtered = await repository.search(
        request_type(
            limit=50, query=query, filter_=filter_type(entity_id=[candidate.entity_id])
        )
    )
    assert filtered.items
    assert all(item.entity_id == candidate.entity_id for item in filtered.items)
    # Include references to guarantee multiple results for both endpoints.
    query = query.model_copy(update={"exclude_reference_face_id": False})
    first = await repository.search(request_type(limit=1, query=query))
    assert first.cursor
    next_page = await repository.search(
        request_type(limit=1, query=query, cursor=first.cursor)
    )
    assert next_page.items and next_page.items != first.items
    for changes in (
        {"entity_annotations": [EntityAnnotation.name]},
        {"entity_id": candidate.entity_id},
    ):
        with pytest.raises(ValueError, match="different query"):
            await repository.search(
                request_type(
                    limit=1, cursor=first.cursor, query=query.model_copy(update=changes)
                )
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["faces", "entities"])
async def test_http_entity_discovery_and_numerical_errors(discovery, endpoint):
    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient
    from people_gator_api.routes.v1 import router
    from people_gator_api.services.auth_service import get_auth_context
    from people_gator_api.services.database_service import get_database

    db, reference, _, empty, refs, zero, missing, *_ = discovery
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: db
    app.dependency_overrides[get_auth_context] = lambda: discovery[-2]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        path = f"/api/v1/search-{endpoint}"
        base = {"query.face_embedding_model": MODEL}
        for params in (
            {"query.entity_id": str(reference.entity_id)},
            {
                "query.entity_id": str(reference.entity_id),
                "query.entity_annotations": "faces",
            },
            {
                "query.entity_id": str(reference.entity_id),
                "query.entity_annotations": "aliases",
            },
            {
                "query.entity_id": str(reference.entity_id),
                "query.entity_annotations": "name",
            },
            {"query.face_id": str(refs[0].detection_id)},
        ):
            response = await client.get(path, params={**base, **params})
            assert response.status_code == 200, response.text
            assert all(
                item["face_score"] is None or math.isfinite(item["face_score"])
                for item in response.json()["items"]
            )
        for params in (
            {"query.entity_id": str(uuid.uuid4())},
            {
                "query.entity_id": str(empty.entity_id),
                "query.entity_annotations": "faces",
            },
            {
                "query.entity_id": str(reference.entity_id),
                "query.entity_annotations": "unsupported",
            },
            {"query.text": "Useful", "query.entity_annotations": "name"},
            {"query.face_id": str(zero.detection_id)},
            {"query.face_id": str(missing.detection_id)},
        ):
            response = await client.get(path, params={**base, **params})
            assert response.status_code == 422, response.text


@pytest.mark.asyncio
async def test_entity_search_resolves_beyond_one_hundred_linked_faces(discovery):
    from people_gator_api.schemas.search import EntitySearchQuery
    from people_gator_api.schemas.faces import FaceListRequest, FaceListFilter

    db, _, candidate, _, _, _, _, useful, _, actor, page = discovery
    reference = await db.entities.create(
        EntityCreateRequest(entity_type="person", name="Large reference"), actor
    )
    faces = await db.faces.create_batch(
        [
            FaceCreateRequest(
                identifier=f"large-{i}",
                bounding_box=BoundingBox(x=1, y=1, width=10, height=10),
                confidence=0.9,
                keypoints=[Keypoint(type=t, x=2, y=2) for t in FaceKeypointType],
                source_id=page.source_id,
                entity_id=reference.entity_id,
                embeddings=[
                    FaceEmbedding(model_identifier=MODEL, vector=[1.0, i / 1000])
                ],
            )
            for i in range(105)
        ],
        actor,
    )
    first = await db.faces.list(
        FaceListRequest(
            limit=100, filter_=FaceListFilter(entity_id=[reference.entity_id])
        )
    )
    assert first.cursor and len(first.items) == 100
    query = EntitySearchQuery(
        entity_id=reference.entity_id,
        entity_annotations=["faces"],
        face_embedding_model=MODEL,
    )
    entities = await db.entities.search(SearchEntitiesRequest(limit=50, query=query))
    assert (
        next(
            item for item in entities.items if item.entity_id == candidate.entity_id
        ).face_score
        > 0.99
    )
    hits = await db.faces.search(SearchFacesRequest(limit=50, query=query))
    assert useful.detection_id in {item.detection_id for item in hits.items}
    # Exact resolution is intentionally separate from representative reduction.
    from people_gator_api.persistence.postgres.search_resolution import (
        resolve_entity_search,
    )

    resolved = await resolve_entity_search(
        db.entities._session, SearchEntitiesRequest(limit=50, query=query)
    )
    assert set(resolved.query.face_id) == {face.detection_id for face in faces}


@pytest.mark.asyncio
async def test_face_text_candidates_bound_fanout_and_apply_filters_before_limit(discovery):
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.persistence.postgres.utils import TEXT_SEARCH_CANDIDATE_LIMIT

    db, _, candidate, _, _, _, _, useful, _, actor, page = discovery
    template = FaceCreateRequest(
        source_id=page.source_id, entity_id=candidate.entity_id,
        identifier="Catalogue Witness", confidence=0.5,
        bounding_box=useful.bounding_box, keypoints=useful.keypoints,
    )
    created = await db.faces.create_batch([template] * (TEXT_SEARCH_CANDIDATE_LIMIT + 5), actor)
    from people_gator_api.schemas.entities import EntityPatchRequest
    await db.entities.patch(candidate.entity_id, EntityPatchRequest(aliases=["Catalogue Alias"]), actor)
    # Each branch is independently bounded, even when one identity has many faces.
    for term in ("Catalogue Witness", "Useful Portrait", "Catalogue Alias"):
        result = await db.faces.search(SearchFacesRequest(
            query=QueryBase(text=[term]), limit=0, return_total_count=True,
        ))
        assert TEXT_SEARCH_CANDIDATE_LIMIT <= result.total_count < len(created)
        scores = await db.faces._text_scores(SearchFacesRequest(query=QueryBase(text=[term]), limit=1), [])
        special = next(face for face in created if face.detection_id not in scores)
        filtered = await db.faces.search(SearchFacesRequest(
            query=QueryBase(text=[term]), limit=100,
            filter_=FaceListFilter(detection_id=[special.detection_id]),
        ))
        assert [face.detection_id for face in filtered.items] == [special.detection_id]
    # Unassigned identifiers remain searchable without an entity or embedding.
    unassigned = await db.faces.create(template.model_copy(update={
        "entity_id": None, "identifier": "Standalone Identifier", "confidence": 0.99,
    }), actor)
    result = await db.faces.search(SearchFacesRequest(
        query=QueryBase(text=["Standalone Identifier"]), limit=10,
    ))
    assert result.items[0].detection_id == unassigned.detection_id
    assert result.items[0].text_score == 1 and result.items[0].face_score is None


@pytest.mark.asyncio
async def test_face_text_candidate_predicates_can_use_all_three_gin_indexes(discovery):
    from sqlalchemy import text
    from sqlalchemy.dialects import postgresql
    from people_gator_api.persistence.postgres.utils import face_text_candidates

    db = discovery[0]
    # Tiny fixtures naturally choose sequential scans. Disable that preference
    # only to prove all predicate branches have usable indexes in the real schema.
    await db.faces._session.execute(text("SET LOCAL enable_seqscan = off"))
    await db.faces._session.execute(text("SET LOCAL enable_indexscan = off"))
    statement = face_text_candidates("Useful Portrait", [])
    compiled = statement.compile(
        dialect=postgresql.dialect(paramstyle="named"), compile_kwargs={"literal_binds": True},
    )
    plan = await db.faces._session.execute(text("EXPLAIN " + str(compiled)))
    plan_text = "\n".join(row[0] for row in plan)
    for name in ("faces_identifier_trgm", "entities_name_trgm", "aliases_name_trgm"):
        assert name in plan_text
    assert plan_text.count("Limit") == 3
