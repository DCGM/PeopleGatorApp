"""ArcFace-aligned face crops rendered from the face's original source image.

The detected face keypoints are aligned to the standard 5-point ArcFace
reference template (as used for 112x112 recognition crops), but the output
keeps the *original* image scale: only rotation and translation are applied
to the reference template, never a resize. This yields a crop whose pixel
density matches the source image instead of being resampled to a fixed
112x112 canvas.
"""

import asyncio
import io
import logging
import uuid

import numpy as np
from PIL import Image
from pydantic import BaseModel
from weaviate import WeaviateAsyncClient

from people_gator_api.schemas.entities import FaceKeypoint, FaceResponse
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import PageSourceMetadata
from people_gator_api.services.crud_services.annotation_service import get_face
from people_gator_api.services.crud_services.image_content_service import get_image_content
from people_gator_api.services.crud_services.page_image_service import get_page_image
from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
    get_source,
)
from people_gator_api.settings import AlignedFaceCropSettings, settings
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)

_JPEG_MEDIA_TYPE = "image/jpeg"

# Documented keypoint order: left_eye, right_eye, nose, left_mouth_corner,
# right_mouth_corner (see people-gator-data-models instructions).
_REQUIRED_KEYPOINT_TYPES = (
    "left_eye",
    "right_eye",
    "nose",
    "left_mouth_corner",
    "right_mouth_corner",
)

# Standard ArcFace 5-point reference template for a 112x112 output canvas.
_ARCFACE_REFERENCE_112 = np.array(
    [
        [38.2946, 51.6963],
        [73.5318, 51.5014],
        [56.0252, 71.7366],
        [41.5493, 92.3655],
        [70.7299, 92.2041],
    ],
    dtype=np.float64,
)


class AlignedFaceCropContent(BaseModel):
    """One rendered aligned face crop ready for an HTTP response."""

    content: bytes
    media_type: str


def _reference_keypoints(crop_cfg: AlignedFaceCropSettings) -> np.ndarray:
    """Scale the 112x112 ArcFace template to the configured reference size."""
    scale = np.array(
        [
            crop_cfg.reference_width / 112.0,
            crop_cfg.reference_height / 112.0,
        ],
        dtype=np.float64,
    )
    return _ARCFACE_REFERENCE_112 * scale


def _ordered_keypoints(keypoints: list[FaceKeypoint]) -> np.ndarray:
    """Return the 5 required keypoints as an ``(5, 2)`` array in template order."""
    by_type = {keypoint.type: (keypoint.x, keypoint.y) for keypoint in keypoints}
    missing = [kp_type for kp_type in _REQUIRED_KEYPOINT_TYPES if kp_type not in by_type]
    if missing:
        raise SourceResolutionError(
            f"face is missing required keypoints for alignment: {', '.join(missing)}",
            status_code=422,
            code="insufficient_keypoints",
        )
    return np.array(
        [by_type[kp_type] for kp_type in _REQUIRED_KEYPOINT_TYPES],
        dtype=np.float64,
    )


def _similarity_transform(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Least-squares similarity transform (Umeyama) with ``dst ~= scale * R @ src + t``."""
    point_count = src.shape[0]
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_centered = src - src_mean
    dst_centered = dst - dst_mean
    covariance = (dst_centered.T @ src_centered) / point_count
    u, singular_values, vt = np.linalg.svd(covariance)
    sign_fix = np.ones(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign_fix[-1] = -1
    rotation = u @ np.diag(sign_fix) @ vt
    src_variance = src_centered.var(axis=0).sum()
    scale = float((singular_values * sign_fix).sum() / src_variance)
    translation = dst_mean - scale * (rotation @ src_mean)
    return rotation, translation, scale


def _render_aligned_crop(
    image_bytes: bytes,
    keypoints: np.ndarray,
    crop_cfg: AlignedFaceCropSettings,
    max_width: int | None,
) -> bytes:
    """Warp ``image_bytes`` so ``keypoints`` align to the ArcFace template.

    Only rotation and translation are applied (scale fixed to 1) so the
    output preserves the original image's pixel scale; the output canvas is
    sized to match, then optionally downscaled to ``max_width``.
    """
    reference = _reference_keypoints(crop_cfg)
    rotation, _, scale = _similarity_transform(keypoints, reference)
    scale_factor = 1.0 / scale

    scaled_reference = reference * scale_factor
    translation = scaled_reference.mean(axis=0) - (rotation @ keypoints.mean(axis=0))

    output_width = max(1, round(crop_cfg.reference_width * scale_factor))
    output_height = max(1, round(crop_cfg.reference_height * scale_factor))

    inverse_rotation = rotation.T
    inverse_translation = -inverse_rotation @ translation
    affine_coefficients = (
        inverse_rotation[0, 0],
        inverse_rotation[0, 1],
        inverse_translation[0],
        inverse_rotation[1, 0],
        inverse_rotation[1, 1],
        inverse_translation[1],
    )

    with Image.open(io.BytesIO(image_bytes)) as source_image:
        if source_image.mode not in ("RGB", "L"):
            source_image = source_image.convert("RGB")
        aligned: Image.Image = source_image.transform(
            (output_width, output_height),
            Image.Transform.AFFINE,
            affine_coefficients,
            resample=Image.Resampling.BICUBIC,
        )

    if max_width is not None and max_width < aligned.width:
        ratio = max_width / aligned.width
        target = (max_width, max(1, round(aligned.height * ratio)))
        aligned = aligned.resize(target, resample=Image.Resampling.BICUBIC)

    buffer = io.BytesIO()
    aligned.save(buffer, format="JPEG", quality=crop_cfg.jpeg_quality)
    return buffer.getvalue()


async def _read_face_source_image(
    client: WeaviateAsyncClient,
    face: FaceResponse,
) -> bytes:
    """Fetch the full-resolution bytes of the image a face was detected in."""
    source = await get_source(client, face.source_id)
    if source is None:
        raise SourceResolutionError(
            "Face source not found", status_code=404, code="not_found"
        )
    if source.source_type == SourceKind.image:
        content, _media_type = await get_image_content(source.uri)
        return content
    if source.source_type == SourceKind.page and isinstance(
        source.metadata, PageSourceMetadata
    ):
        page_image = await get_page_image(
            source.metadata.library,
            source.metadata.document,
            source.metadata.page,
            max_width=None,
        )
        return page_image.content
    raise SourceResolutionError(
        "face source does not resolve to a renderable image",
        status_code=422,
        code="unsupported_source_type",
    )


@trace()
async def get_aligned_face_crop(
    client: WeaviateAsyncClient,
    user_id: uuid.UUID,
    detection_id: uuid.UUID,
    *,
    max_width: int | None = None,
) -> AlignedFaceCropContent:
    """Return one ArcFace-aligned crop for a face detection."""
    face = await get_face(client, user_id, detection_id)
    if face is None:
        raise SourceResolutionError(
            "Face not found", status_code=404, code="not_found"
        )
    crop_cfg = settings.aligned_face_crop
    if max_width is not None and max_width > crop_cfg.max_output_width:
        raise SourceResolutionError(
            "requested max_width exceeds the configured limit",
            status_code=422,
            code="invalid_max_width",
        )
    keypoints = _ordered_keypoints(face.keypoints)
    image_bytes = await _read_face_source_image(client, face)
    content = await asyncio.to_thread(
        _render_aligned_crop, image_bytes, keypoints, crop_cfg, max_width
    )
    return AlignedFaceCropContent(content=content, media_type=_JPEG_MEDIA_TYPE)
