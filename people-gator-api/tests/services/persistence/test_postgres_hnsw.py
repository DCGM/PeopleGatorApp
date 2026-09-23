from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from people_gator_api.models import FaceModel, Page, face_embedding_hnsw_index
from people_gator_api.persistence.postgres import (
    PostgresEntityRepository,
    PostgresFaceModelRepository,
    PostgresFaceRepository,
    PostgresSourceRepository,
)
from people_gator_api.schemas.enums import DEFAULT_FACE_EMBEDDING_MODEL
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.search import (
    QueryBase,
    SearchEntitiesRequest,
    SearchFacesRequest,
    SearchPagesRequest,
)


def test_face_embedding_hnsw_index_uses_cosine_vector_column() -> None:
    index = face_embedding_hnsw_index(DEFAULT_FACE_EMBEDDING_MODEL, 512)
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))

    assert "USING hnsw" in ddl
    assert "CAST(embedding AS VECTOR(512)) vector_cosine_ops" in ddl
    assert "WHERE model_id = 'vit_small_patch8_gap_112.cosface_ms1mv3'" in ddl
    assert "m = 16" in ddl
    assert "ef_construction = 64" in ddl


def test_face_model_registration_schema_normalizes_and_validates() -> None:
    payload = FaceModelRegisterRequest(
        model_stub="  face/model-v1  ",
        embedding_dim=512,
    )
    assert payload.model_stub == "face/model-v1"

    with pytest.raises(ValidationError):
        FaceModelRegisterRequest(model_stub="model", embedding_dim=0)


@pytest.mark.asyncio
async def test_register_face_model_is_idempotent_for_same_dimension() -> None:
    session = AsyncMock()
    session.get.return_value = FaceModel(stub="face/model-v1", embedding_dim=768)
    repository = PostgresFaceModelRepository(session)

    response = await repository.register(
        FaceModelRegisterRequest(model_stub="face/model-v1", embedding_dim=768)
    )

    assert response.model_stub == "face/model-v1"
    assert response.embedding_dim == 768
    session.connection.return_value.run_sync.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_register_face_model_rejects_dimension_change() -> None:
    session = AsyncMock()
    session.get.return_value = FaceModel(stub="face/model-v1", embedding_dim=512)
    repository = PostgresFaceModelRepository(session)

    with pytest.raises(ValueError, match="already registered with dimension 512"):
        await repository.register(
            FaceModelRegisterRequest(model_stub="face/model-v1", embedding_dim=768)
        )

    session.connection.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_entity_face_scores_use_lateral_hnsw_candidates() -> None:
    reference_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    vector = [1.0] + [0.0] * 511

    reference_rows = Mock()
    reference_rows.all.return_value = [(reference_id, vector)]
    score_rows = Mock()
    score_rows.all.return_value = [(candidate_id, 0.75)]
    session = AsyncMock()
    session.get.return_value = FaceModel(
        stub=DEFAULT_FACE_EMBEDDING_MODEL,
        embedding_dim=512,
    )
    session.execute.side_effect = [reference_rows, Mock(), score_rows]
    session.scalars.return_value = [candidate_id]

    repository = PostgresEntityRepository(session)
    scores = await repository._face_scores(  # pyright: ignore[reportPrivateUsage]
        SearchEntitiesRequest(
            query=QueryBase(face_id=[reference_id]),
            limit=10,
        ),
        [],
    )

    assert scores == {candidate_id: 0.75}
    candidate_statement = session.scalars.await_args.args[0]
    compiled = candidate_statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "JOIN LATERAL" in sql
    assert "<=> query_vectors.embedding" in sql
    assert "ORDER BY" in sql
    assert 200 in compiled.params.values()
    assert str(session.execute.await_args_list[1].args[0]) == (
        "SET LOCAL hnsw.ef_search = 400"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("repository_type", "request_type", "search_method", "expected_table"),
    [
        (PostgresFaceRepository, SearchFacesRequest, "_face_scores", "pg_demo_faces"),
        (
            PostgresSourceRepository,
            SearchPagesRequest,
            "_source_face_scores",
            "pg_demo_pages",
        ),
    ],
)
async def test_other_face_score_paths_use_lateral_hnsw_candidates(
    repository_type: type[PostgresFaceRepository] | type[PostgresSourceRepository],
    request_type: type[SearchFacesRequest] | type[SearchPagesRequest],
    search_method: str,
    expected_table: str,
) -> None:
    reference_id = uuid.uuid4()
    candidate_id = uuid.uuid4()
    vector = [1.0] + [0.0] * 511
    reference_rows = Mock()
    reference_rows.all.return_value = [(reference_id, vector)]
    score_rows = Mock()
    score_rows.all.return_value = [(candidate_id, 0.5)]
    session = AsyncMock()
    session.get.return_value = FaceModel(
        stub=DEFAULT_FACE_EMBEDDING_MODEL,
        embedding_dim=512,
    )
    session.execute.side_effect = [reference_rows, Mock(), score_rows]
    session.scalars.return_value = [candidate_id]
    repository = repository_type(session)
    request = request_type(query=QueryBase(face_id=[reference_id]), limit=10)

    method = getattr(repository, search_method)
    if isinstance(repository, PostgresSourceRepository):
        scores = await method(Page, request, [])
    else:
        scores = await method(request, [])

    assert scores == {candidate_id: 0.5}
    candidate_statement = session.scalars.await_args.args[0]
    compiled = candidate_statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "JOIN LATERAL" in sql
    assert "<=> query_vectors.embedding" in sql
    assert expected_table in sql
    assert 200 in compiled.params.values()
