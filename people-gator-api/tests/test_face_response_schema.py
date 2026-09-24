import uuid

from people_gator_api.schemas.faces import BoundingBox, FaceResponse, Keypoint


def _face_response(**changes: object) -> FaceResponse:
    values: dict[str, object] = {
        "detection_id": uuid.uuid4(),
        "source_id": uuid.uuid4(),
        "bounding_box": BoundingBox(x=1, y=2, width=3, height=4),
        "keypoints": [
            Keypoint(type=f"k{index}", x=float(index), y=float(index))
            for index in range(5)
        ],
        "user_id": uuid.uuid4(),
        "confidence": 0.9,
    }
    values.update(changes)
    return FaceResponse.model_validate(values)


def test_face_response_lists_embedding_models_without_vectors() -> None:
    response = _face_response(embeddings=["model-b", "model-a"])

    assert response.model_dump()["embeddings"] == ["model-b", "model-a"]


def test_face_response_defaults_to_no_embedding_models() -> None:
    assert _face_response().embeddings == []
