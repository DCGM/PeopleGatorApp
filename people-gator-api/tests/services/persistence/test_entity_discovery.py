"""Synthetic regressions for discovery's numerical and entity reference contracts."""

import math
import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.faces import BoundingBox, FaceCreateRequest, FaceEmbedding, Keypoint
from people_gator_api.schemas.enums import FaceKeypointType
from people_gator_api.schemas.search import QueryBase, SearchEntitiesRequest, SearchFacesRequest
from people_gator_api.schemas.sources import PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest

MODEL = "discovery-regression-2d"


@pytest_asyncio.fixture
async def discovery(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor = await db.users.get_or_create(UserCreateRequest(
            display_name="Synthetic discovery", is_active=True,
            external_subject="discovery", external_issuer="test",
        ))
        await db.face_models.register(FaceModelRegisterRequest(model_stub=MODEL, embedding_dim=2))
        page, _ = await db.sources.get_or_create_page(PageCreateRequest(
            library="synthetic", document_id=uuid.uuid4(), page_id=uuid.uuid4(),
        ))
        reference, candidate, empty = await db.entities.create_batch([
            EntityCreateRequest(entity_type="person", name="Zephyr Cartographer", aliases=["Saffron Navigator"]),
            EntityCreateRequest(entity_type="person", name="Useful Portrait"),
            EntityCreateRequest(entity_type="person", name="Empty Signal"),
        ], actor)

        async def face(key, vector, entity=reference):
            return await db.faces.create(FaceCreateRequest(
                identifier=key, bounding_box=BoundingBox(x=1, y=1, width=10, height=10),
                confidence=0.9, keypoints=[Keypoint(type=t, x=2, y=2) for t in FaceKeypointType], source_id=page.source_id,
                entity_id=entity.entity_id if entity else None,
                embeddings=[FaceEmbedding(model_identifier=MODEL, vector=vector)] if vector is not None else [],
            ), actor)

        refs = [await face(f"reference-{i}", [1.0, i / 100]) for i in range(12)]
        zero_reference = await face("zero-reference", [0.0, 0.0])
        missing_reference = await face("missing-reference", None)
        useful = await face("useful", [1.0, 0.0], candidate)
        zero_candidate = await face("zero-candidate", [0.0, 0.0], candidate)
        yield db, reference, candidate, empty, refs, zero_reference, missing_reference, useful, zero_candidate, actor, page


@pytest.mark.asyncio
@pytest.mark.parametrize("aggregation", ["min", "max", "average"])
@pytest.mark.parametrize("many", [False, True])
async def test_zero_candidate_does_not_poison_usable_results(discovery, aggregation, many):
    db, _, candidate, _, refs, _, _, useful, zero_candidate, *_ = discovery
    query = QueryBase(face_id=[item.detection_id for item in (refs if many else refs[:1])],
                      face_embedding_model=MODEL, score_aggregation=aggregation)
    entities = await db.entities.search(SearchEntitiesRequest(query=query, limit=50))
    hit = next(item for item in entities.items if item.entity_id == candidate.entity_id)
    assert math.isfinite(hit.face_score) and hit.face_score > 0.99
    assert zero_candidate.detection_id not in hit.matched_detection_ids
    faces = await db.faces.search(SearchFacesRequest(query=query, limit=50))
    assert useful.detection_id in {item.detection_id for item in faces.items}
    assert zero_candidate.detection_id not in {item.detection_id for item in faces.items}
    assert all(math.isfinite(item.face_score) for item in faces.items)


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["faces", "entities"])
async def test_explicit_unusable_reference_is_strict(discovery, endpoint):
    db, _, _, _, refs, zero, missing, *_ = discovery
    request_type = SearchFacesRequest if endpoint == "faces" else SearchEntitiesRequest
    repository = getattr(db, endpoint)
    for face, message in ((zero, "unusable cosine"), (missing, "lacks embedding")):
        with pytest.raises(ValueError, match=message):
            await repository.search(request_type(limit=50, query=QueryBase(
                face_id=[refs[0].detection_id, face.detection_id], face_embedding_model=MODEL,
            )))
