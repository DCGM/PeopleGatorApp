from __future__ import annotations

import asyncio
import os
import uuid
from typing import cast

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
import pytest
from botocore.exceptions import ClientError

from people_gator_api.schemas.entities import BoundingBox, FaceKeypoint, FaceResponse
from people_gator_api.services.crud_services import aligned_face_crop_service
from people_gator_api.services.crud_services.aligned_face_crop_service import (
    AlignedFaceCropContent,
    get_aligned_face_crop,
)
from people_gator_api.settings import AlignedFaceCropSettings


_USER_ID = uuid.UUID("0d871e87-e57e-44e3-88be-e0b492c956d2")
_DETECTION_ID = uuid.UUID("c018de6a-98c0-4526-93b0-9e45bf462203")
_SOURCE_ID = uuid.UUID("3acb3510-cf49-4d62-9dc0-0f9cce68bdf7")


def _face(*, left_eye_x: float = 38.0) -> FaceResponse:
    return FaceResponse(
        detection_id=_DETECTION_ID,
        source_id=_SOURCE_ID,
        bounding_box=BoundingBox(x=10, y=20, width=100, height=100),
        keypoints=[
            FaceKeypoint(type="left_eye", x=left_eye_x, y=52.0),
            FaceKeypoint(type="right_eye", x=74.0, y=52.0),
            FaceKeypoint(type="nose", x=56.0, y=72.0),
            FaceKeypoint(type="left_mouth_corner", x=42.0, y=92.0),
            FaceKeypoint(type="right_mouth_corner", x=71.0, y=92.0),
        ],
        user_id=_USER_ID,
        confidence=0.99,
    )


def test_crop_cache_is_invalidated_when_keypoint_position_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    crop_cfg = AlignedFaceCropSettings(
        cache_enabled=True,
        cache_key_prefix="face-crop-cache",
    )
    monkeypatch.setattr(
        aligned_face_crop_service.settings, "aligned_face_crop", crop_cfg
    )

    current_face = _face()
    objects: dict[str, bytes] = {}
    source_reads = 0
    renders = 0

    async def fake_get_face(*_args: object) -> FaceResponse:
        return current_face

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

    monkeypatch.setattr(aligned_face_crop_service, "get_face", fake_get_face)
    monkeypatch.setattr(
        aligned_face_crop_service, "_read_face_source_image", fake_read_source
    )
    monkeypatch.setattr(
        aligned_face_crop_service, "_render_aligned_crop", fake_render
    )
    monkeypatch.setattr(aligned_face_crop_service, "read_bytes", fake_read_bytes)
    monkeypatch.setattr(aligned_face_crop_service, "write_bytes", fake_write_bytes)

    async def scenario() -> tuple[
        AlignedFaceCropContent,
        AlignedFaceCropContent,
        AlignedFaceCropContent,
    ]:
        nonlocal current_face
        first = await get_aligned_face_crop(
            None, _USER_ID, _DETECTION_ID  # type: ignore[arg-type]
        )
        pending = list(
            aligned_face_crop_service._background_cache_writes  # pyright: ignore[reportPrivateUsage]
        )
        await asyncio.gather(*pending)
        second = await get_aligned_face_crop(
            None, _USER_ID, _DETECTION_ID  # type: ignore[arg-type]
        )

        current_face = _face(left_eye_x=39.0)
        changed = await get_aligned_face_crop(
            None, _USER_ID, _DETECTION_ID  # type: ignore[arg-type]
        )
        pending = list(
            aligned_face_crop_service._background_cache_writes  # pyright: ignore[reportPrivateUsage]
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
        aligned_face_crop_service.settings,
        "aligned_face_crop",
        AlignedFaceCropSettings(cache_enabled=False),
    )

    async def fake_get_face(*_args: object) -> FaceResponse:
        return _face()

    async def fake_read_source(*_args: object) -> bytes:
        return b"source-image"

    def fake_render(*_args: object) -> bytes:
        return b"rendered"

    async def fail_cache_access(*_args: object) -> bytes:
        raise AssertionError("disabled cache must not access object storage")

    monkeypatch.setattr(aligned_face_crop_service, "get_face", fake_get_face)
    monkeypatch.setattr(
        aligned_face_crop_service, "_read_face_source_image", fake_read_source
    )
    monkeypatch.setattr(
        aligned_face_crop_service, "_render_aligned_crop", fake_render
    )
    monkeypatch.setattr(aligned_face_crop_service, "read_bytes", fail_cache_access)
    monkeypatch.setattr(aligned_face_crop_service, "write_bytes", fail_cache_access)

    result = cast(
        AlignedFaceCropContent,
        asyncio.run(
            get_aligned_face_crop(None, _USER_ID, _DETECTION_ID)  # type: ignore[arg-type]
        ),
    )

    assert result == AlignedFaceCropContent(
        content=b"rendered",
        media_type="image/jpeg",
        cache_hit=False,
    )
