from __future__ import annotations

import asyncio
import io
import os
import uuid
from typing import Never
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__WEAVIATE__GRPC_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")

import numpy as np
from numpy.typing import NDArray
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from PIL import Image, ImageDraw
from botocore.exceptions import ClientError
from pydantic import AnyUrl

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.faces import BoundingBox, FaceResponse, FaceKeypoint, FaceKeypointType
from people_gator_api.schemas.sources import GenericSourceResponse, page_url
from people_gator_api.media import aligned_face_crop
from people_gator_api.media.aligned_face_crop import (
    AlignedFaceCropContent,
    get_aligned_face_crop,
)
from people_gator_api.settings import AlignedFaceCropSettings
from people_gator_api.media.errors import SourceResolutionError


_USER_ID = uuid.UUID("0d871e87-e57e-44e3-88be-e0b492c956d2")
_DETECTION_ID = uuid.UUID("c018de6a-98c0-4526-93b0-9e45bf462203")
_SOURCE_ID = uuid.UUID("3acb3510-cf49-4d62-9dc0-0f9cce68bdf7")


def _face(*, left_eye_x: float = 38.0) -> FaceResponse:
    return FaceResponse(
        detection_id=_DETECTION_ID,
        source_id=_SOURCE_ID,
        bounding_box=BoundingBox(x=10, y=20, width=100, height=100),
        keypoints=[
            FaceKeypoint(type=FaceKeypointType.left_eye, x=left_eye_x, y=52.0),
            FaceKeypoint(type=FaceKeypointType.right_eye, x=74.0, y=52.0),
            FaceKeypoint(type=FaceKeypointType.nose, x=56.0, y=72.0),
            FaceKeypoint(type=FaceKeypointType.left_mouth_corner, x=42.0, y=92.0),
            FaceKeypoint(type=FaceKeypointType.right_mouth_corner, x=71.0, y=92.0),
        ],
        user_id=_USER_ID,
        confidence=0.99,
    )


def _source() -> GenericSourceResponse:
    document_id = uuid.UUID("57877a35-c00a-42d2-9515-05a8a6843d8f")
    page_id = uuid.UUID("88400acc-fb2f-41af-ae63-a1e77a21b1db")
    return GenericSourceResponse(
        source_id=_SOURCE_ID,
        source_type=SourceKind.page,
        url=AnyUrl(page_url("mzk", document_id, page_id)),
        library="mzk",
        document_id=document_id,
        page_id=page_id,
    )


def _image() -> bytes:
    image: Image.Image = Image.new("RGB", (256, 256), "white")
    # A landmark marker verifies alignment as well as dimensions.
    image.putpixel((56, 72), (0, 0, 0))
    buffer: io.BytesIO = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _coincident_face() -> FaceResponse:
    face: FaceResponse = _face()
    for point in face.keypoints:
        point.x = point.y = 64.0
    return face


@pytest.mark.parametrize("cache_enabled", [False, True])
@pytest.mark.parametrize("max_width", [None, 256])
def test_coincident_landmarks_return_structured_http_error_without_cache_write(
    monkeypatch: pytest.MonkeyPatch, cache_enabled: bool, max_width: int | None,
) -> None:
    from people_gator_api.routes.v1.annotations import router
    from people_gator_api.services import auth_service, database_service

    monkeypatch.setattr(aligned_face_crop.settings, "aligned_face_crop",
                        AlignedFaceCropSettings(cache_enabled=cache_enabled))
    monkeypatch.setattr(aligned_face_crop, "_read_face_source_image", AsyncMock(return_value=_image()))
    read_cache: AsyncMock = AsyncMock(side_effect=FileNotFoundError)
    write_cache: AsyncMock = AsyncMock()
    monkeypatch.setattr(aligned_face_crop, "read_bytes", read_cache)
    monkeypatch.setattr(aligned_face_crop, "write_bytes", write_cache)
    app: FastAPI = FastAPI()
    app.include_router(router, prefix="/api/v1")

    def get_database() -> SimpleNamespace:
        return SimpleNamespace(
            faces=SimpleNamespace(get=AsyncMock(return_value=_coincident_face())),
            sources=SimpleNamespace(lookup=AsyncMock(return_value=_source())),
        )

    def get_auth_context() -> SimpleNamespace:
        return SimpleNamespace(user_id=_USER_ID)

    app.dependency_overrides[database_service.get_database] = get_database
    app.dependency_overrides[auth_service.get_auth_context] = get_auth_context
    with TestClient(app) as client:
        response: Response = client.get(
            f"/api/v1/faces/{_DETECTION_ID}/aligned_crop",
            params={} if max_width is None else {"max_width": max_width},
        )
    assert response.status_code == 422
    assert response.json() == {"detail": {
        "code": "invalid_face_keypoints",
        "message": "face keypoints cannot produce a usable alignment",
    }}
    assert read_cache.await_count == int(cache_enabled)
    write_cache.assert_not_called()


@pytest.mark.parametrize("points", [
    np.full((5, 2), 64.0),
    np.full((5, 2), 1e308),  # mean overflow
    np.array([[1e200, -1e200], [-1e200, 1e200], [0, 0], [1, 1], [2, 2]]),  # variance overflow
    np.array([[1e-200, 0], [-1e-200, 0], [0, 0], [0, 1e-200], [0, -1e-200]]),  # variance underflow
    aligned_face_crop._ARCFACE_REFERENCE_112 * 1e6,  # unusable native canvas
    aligned_face_crop._ARCFACE_REFERENCE_112 * 100,  # pixel budget, within JPEG dimensions
    np.full((5, 2), np.nan),
])
def test_unusable_geometry_is_a_media_error_before_image_allocation(
    points: NDArray[np.float64],
) -> None:
    # Invalid image bytes ensure validation finishes before opening/allocating an image.
    with pytest.raises(SourceResolutionError) as error:
        aligned_face_crop._render_aligned_crop(b"", points, AlignedFaceCropSettings(), 256)
    assert (error.value.status_code, error.value.code) == (422, "invalid_face_keypoints")


def test_svd_failure_is_a_geometry_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object) -> Never:
        raise np.linalg.LinAlgError("SVD did not converge")

    monkeypatch.setattr(np.linalg, "svd", fail)
    with pytest.raises(SourceResolutionError, match="usable alignment"):
        aligned_face_crop._render_aligned_crop(
            _image(), aligned_face_crop._ARCFACE_REFERENCE_112,
            AlignedFaceCropSettings(), None,
        )


@pytest.mark.parametrize("scale", [0.0, -1.0, float("nan"), float("inf"), 5e-324, 1e-307])
def test_invalid_derived_scale_is_rejected(monkeypatch: pytest.MonkeyPatch, scale: float) -> None:
    def transform(*_args: object) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
        return np.eye(2), np.zeros(2), scale

    monkeypatch.setattr(aligned_face_crop, "_similarity_transform", transform)
    with pytest.raises(SourceResolutionError, match="usable alignment"):
        aligned_face_crop._render_aligned_crop(
            b"", aligned_face_crop._ARCFACE_REFERENCE_112, AlignedFaceCropSettings(), 256,
        )


@pytest.mark.parametrize("rotation,translation", [
    (np.full((2, 2), np.nan), np.zeros(2)),
    (np.eye(2), np.full(2, np.inf)),
])
def test_nonfinite_transform_is_rejected(
    monkeypatch: pytest.MonkeyPatch, rotation: NDArray[np.float64], translation: NDArray[np.float64],
) -> None:
    def transform(*_args: object) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
        return rotation, translation, 1.0

    monkeypatch.setattr(aligned_face_crop, "_similarity_transform", transform)
    with pytest.raises(SourceResolutionError, match="usable alignment"):
        aligned_face_crop._render_aligned_crop(
            b"", aligned_face_crop._ARCFACE_REFERENCE_112, AlignedFaceCropSettings(), 256,
        )


@pytest.mark.parametrize("size,max_width,expected", [
    (1, None, 112), (2, None, 224), (2, 100, 100), (1, 256, 112), (1e-3, None, 1),
])
@pytest.mark.parametrize("angle", [0.0, 0.7])
def test_valid_small_rotated_and_native_scale_crops(
    size: float, max_width: int | None, expected: int, angle: float,
) -> None:
    rotation: NDArray[np.float64] = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    points: NDArray[np.float64] = size * aligned_face_crop._ARCFACE_REFERENCE_112 @ rotation.T + 20
    content: bytes = aligned_face_crop._render_aligned_crop(
        _image(), points, AlignedFaceCropSettings(), max_width,
    )
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        assert image.format == "JPEG" and image.size == (expected, expected)


def test_valid_alignment_preserves_landmark_position() -> None:
    content: bytes = aligned_face_crop._render_aligned_crop(
        _image(), aligned_face_crop._ARCFACE_REFERENCE_112,
        AlignedFaceCropSettings(), None,
    )
    with Image.open(io.BytesIO(content)) as image:
        assert max(image.getpixel((56, 72))) < 40
        assert min(image.getpixel((60, 72))) > 230


@pytest.mark.parametrize("points", [
    aligned_face_crop._ARCFACE_REFERENCE_112 * 1e-150,
    np.column_stack((np.arange(5) * 5 + 40, np.full(5, 70))),
])
def test_representable_tiny_and_collinear_geometry_is_not_arbitrarily_rejected(
    points: NDArray[np.float64],
) -> None:
    content: bytes = aligned_face_crop._render_aligned_crop(
        _image(), points, AlignedFaceCropSettings(), None,
    )
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        assert image.format == "JPEG" and image.width > 0 and image.height > 0


def test_rotated_alignment_moves_landmark_to_reference_position() -> None:
    angle: float = 0.7
    rotation: NDArray[np.float64] = np.array(
        [[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]]
    )
    points: NDArray[np.float64] = aligned_face_crop._ARCFACE_REFERENCE_112 @ rotation.T + 60
    image: Image.Image = Image.new("RGB", (256, 256), "white")
    x: np.float64
    y: np.float64
    x, y = points[2]  # Nose in the rotated source.
    ImageDraw.Draw(image).rectangle((x - 3, y - 3, x + 3, y + 3), fill="black")
    buffer: io.BytesIO = io.BytesIO()
    image.save(buffer, format="PNG")
    content: bytes = aligned_face_crop._render_aligned_crop(
        buffer.getvalue(), points, AlignedFaceCropSettings(), None,
    )
    with Image.open(io.BytesIO(content)) as aligned:
        assert max(aligned.getpixel((56, 72))) < 40
        assert min(aligned.getpixel((65, 72))) > 230


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_unrelated_transform_failure_is_not_classified_as_geometry(
    monkeypatch: pytest.MonkeyPatch, error_type: type[ValueError] | type[RuntimeError],
) -> None:
    def fail(*_args: object) -> Never:
        raise error_type("unrelated implementation failure")

    monkeypatch.setattr(aligned_face_crop, "_similarity_transform", fail)
    with pytest.raises(error_type, match="unrelated implementation failure"):
        aligned_face_crop._render_aligned_crop(
            b"", aligned_face_crop._ARCFACE_REFERENCE_112, AlignedFaceCropSettings(), None,
        )


def test_unrelated_render_failure_is_not_classified_as_keypoint_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> Never:
        raise OSError("storage/image failure")

    monkeypatch.setattr(Image, "open", fail)
    with pytest.raises(OSError, match="storage/image failure"):
        aligned_face_crop._render_aligned_crop(
            _image(), aligned_face_crop._ARCFACE_REFERENCE_112,
            AlignedFaceCropSettings(), None,
        )


def test_real_renderer_cache_miss_hit_and_landmark_edit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aligned_face_crop.settings, "aligned_face_crop",
                        AlignedFaceCropSettings(cache_enabled=True))
    source: AsyncMock = AsyncMock(return_value=_image())
    monkeypatch.setattr(aligned_face_crop, "_read_face_source_image", source)
    objects: dict[str, bytes] = {}

    async def read(key: str) -> bytes:
        if key not in objects:
            raise FileNotFoundError(key)
        return objects[key]

    async def write(key: str, content: bytes) -> None:
        objects[key] = content

    monkeypatch.setattr(aligned_face_crop, "read_bytes", read)
    monkeypatch.setattr(aligned_face_crop, "write_bytes", write)

    async def scenario() -> tuple[
        AlignedFaceCropContent, AlignedFaceCropContent, AlignedFaceCropContent,
    ]:
        first: AlignedFaceCropContent = await get_aligned_face_crop(
            _USER_ID, _face(), _source(), max_width=100,
        )
        await asyncio.gather(*list(aligned_face_crop._background_cache_writes))
        second: AlignedFaceCropContent = await get_aligned_face_crop(
            _USER_ID, _face(), _source(), max_width=100,
        )
        edited: AlignedFaceCropContent = await get_aligned_face_crop(
            _USER_ID, _face(left_eye_x=39), _source(), max_width=100,
        )
        await asyncio.gather(*list(aligned_face_crop._background_cache_writes))
        return first, second, edited

    first: AlignedFaceCropContent
    second: AlignedFaceCropContent
    edited: AlignedFaceCropContent
    first, second, edited = asyncio.run(scenario())
    assert not first.cache_hit and second.cache_hit and not edited.cache_hit
    assert first.content == second.content
    assert len(objects) == source.await_count == 2
    for result in (first, edited):
        with Image.open(io.BytesIO(result.content)) as image:
            image.load()
            assert image.format == "JPEG" and image.size == (100, 100)


@pytest.mark.parametrize("case,code", [
    ("missing", "insufficient_keypoints"),
    ("mismatch", "source_mismatch"),
    ("width", "invalid_max_width"),
])
def test_existing_media_validation_is_preserved(case: str, code: str) -> None:
    face: FaceResponse
    source: GenericSourceResponse
    face, source = _face(), _source()
    if case == "missing":
        face.keypoints = []
    elif case == "mismatch":
        source.source_id = uuid.uuid4()
    with pytest.raises(SourceResolutionError) as error:
        asyncio.run(get_aligned_face_crop(
            _USER_ID, face, source,
            max_width=aligned_face_crop.settings.aligned_face_crop.max_output_width + 1
            if case == "width" else None,
        ))
    assert error.value.status_code == 422 and error.value.code == code


def test_crop_cache_is_invalidated_when_keypoint_position_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crop_cfg = AlignedFaceCropSettings(
        cache_enabled=True,
        cache_key_prefix="face-crop-cache",
    )
    monkeypatch.setattr(
        aligned_face_crop.settings, "aligned_face_crop", crop_cfg
    )

    current_face = _face()
    objects: dict[str, bytes] = {}
    source_reads = 0
    renders = 0

    async def fake_read_source(*_args: object) -> bytes:
        nonlocal source_reads
        source_reads += 1
        return b"source-image"

    def fake_render(
        _image: bytes,
        keypoints: np.ndarray,
        _cfg: AlignedFaceCropSettings,
        _max_width: int | None,
    ) -> bytes:
        nonlocal renders
        renders += 1
        return f"crop-{keypoints[0, 0]}".encode()

    async def fake_read_bytes(key: str) -> bytes:
        if key not in objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        return objects[key]

    async def fake_write_bytes(key: str, data: bytes) -> None:
        objects[key] = data

    monkeypatch.setattr(
        aligned_face_crop, "_read_face_source_image", fake_read_source
    )
    monkeypatch.setattr(
        aligned_face_crop, "_render_aligned_crop", fake_render
    )
    monkeypatch.setattr(aligned_face_crop, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(aligned_face_crop, "write_bytes", fake_write_bytes)

    async def scenario() -> tuple[
        AlignedFaceCropContent,
        AlignedFaceCropContent,
        AlignedFaceCropContent,
    ]:
        nonlocal current_face
        first = await get_aligned_face_crop(_USER_ID, current_face, _source())
        pending = list(
            aligned_face_crop._background_cache_writes  # pyright: ignore[reportPrivateUsage]
        )
        await asyncio.gather(*pending)
        second = await get_aligned_face_crop(_USER_ID, current_face, _source())

        current_face = _face(left_eye_x=39.0)
        changed = await get_aligned_face_crop(_USER_ID, current_face, _source())
        pending = list(
            aligned_face_crop._background_cache_writes  # pyright: ignore[reportPrivateUsage]
        )
        await asyncio.gather(*pending)
        return first, second, changed

    first, second, changed = asyncio.run(scenario())

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.content == first.content == b"crop-38.0"
    assert changed.cache_hit is False
    assert changed.content == b"crop-39.0"
    assert source_reads == 2
    assert renders == 2
    assert len(objects) == 2
    assert all(
        key.startswith(f"face-crop-cache/{_USER_ID}/{_DETECTION_ID}/")
        for key in objects
    )


def test_disabled_crop_cache_always_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        aligned_face_crop.settings,
        "aligned_face_crop",
        AlignedFaceCropSettings(cache_enabled=False),
    )

    async def fake_read_source(*_args: object) -> bytes:
        return b"source-image"

    def fake_render(*_args: object) -> bytes:
        return b"rendered"

    async def fail_cache_access(*_args: object) -> bytes:
        raise AssertionError("disabled cache must not access object storage")

    monkeypatch.setattr(
        aligned_face_crop, "_read_face_source_image", fake_read_source
    )
    monkeypatch.setattr(
        aligned_face_crop, "_render_aligned_crop", fake_render
    )
    monkeypatch.setattr(aligned_face_crop, "read_bytes", fail_cache_access)
    monkeypatch.setattr(aligned_face_crop, "write_bytes", fail_cache_access)

    async def render() -> AlignedFaceCropContent:
        return await get_aligned_face_crop(_USER_ID, _face(), _source())

    result = asyncio.run(render())

    assert result == AlignedFaceCropContent(
        content=b"rendered",
        media_type="image/jpeg",
        cache_hit=False,
    )
