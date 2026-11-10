"""Face embeddings must be usable cosine vectors (#134)."""

import math
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest

from people_gator_api.routes.v1.annotations import router
from people_gator_api.schemas.faces import FaceEmbedding, FacePatchRequest
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database

MODEL = "synthetic-model"


@pytest.mark.parametrize("vector", [[0.0], [0.0, 0.0, 0.0], [-0.0, 0.0]])
def test_zero_vector_is_rejected(vector: list[float]) -> None:
    with pytest.raises(ValidationError, match="must not be all zeros"):
        FaceEmbedding(model_identifier=MODEL, vector=vector)


@pytest.mark.parametrize("vector", [[math.nan, 1.0], [math.inf, 1.0], []])
def test_non_finite_or_empty_vector_is_rejected(vector: list[float]) -> None:
    with pytest.raises(ValidationError):
        FaceEmbedding(model_identifier=MODEL, vector=vector)


@pytest.mark.parametrize("vector", [[1.0, 0.0], [0.0, -1e-200], [1e300, 1e300]])
def test_nonzero_vector_is_accepted(vector: list[float]) -> None:
    assert FaceEmbedding(model_identifier=MODEL, vector=vector).vector == vector


def test_patch_rejects_zero_vector() -> None:
    with pytest.raises(ValidationError, match="must not be all zeros"):
        FacePatchRequest.model_validate(
            {"embeddings": [{"model_identifier": MODEL, "vector": [0.0, 0.0]}]}
        )


def test_face_create_route_rejects_zero_vector_before_storage() -> None:
    app = FastAPI()
    app.include_router(router)

    class UnusedDatabase:
        @property
        def faces(self):
            raise AssertionError("a rejected face must not reach the database")

    app.dependency_overrides[get_database] = UnusedDatabase
    app.dependency_overrides[get_auth_context] = lambda: None
    payload = {
        "identifier": "zero",
        "source_id": str(uuid.uuid4()),
        "bounding_box": {"x": 1, "y": 1, "width": 10, "height": 10},
        "confidence": 0.9,
        "keypoints": [],
        "embeddings": [{"model_identifier": MODEL, "vector": [0.0, 0.0]}],
    }
    with TestClient(app) as client:
        response = client.post("/faces", json=payload)

    assert response.status_code == 422
    assert "must not be all zeros" in response.text
