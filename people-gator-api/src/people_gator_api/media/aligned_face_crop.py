"""ArcFace-aligned face crops rendered from the face's original source image.

The detected face keypoints are aligned to the standard 5-point ArcFace
reference template (as used for 112x112 recognition crops), but the output
keeps the *original* image scale: only rotation and translation are applied
to the reference template, never a resize. This yields a crop whose pixel
density matches the source image instead of being resampled to a fixed
112x112 canvas.

Rendered crops are cached in object storage under a content-addressed key. The
key fingerprints every face/configuration value that affects rendering, so an
edit to a keypoint automatically selects a fresh cache entry.
"""

import asyncio
import hashlib
import io
import json
import logging
import math
import posixpath
import uuid

import numpy as np
from numpy.typing import NDArray
from botocore.exceptions import BotoCoreError, ClientError
from PIL import Image
from pydantic import BaseModel

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.faces import FaceKeypointType, FaceResponse, Keypoint
from people_gator_api.schemas.sources import GenericSourceResponse
from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.media.image_content import get_image_content
from people_gator_api.media.page_image import get_page_image
from people_gator_api.services.filesystem_service import read_bytes, write_bytes
from people_gator_api.settings import AlignedFaceCropSettings, settings
from people_gator_api.utils.opentelemetry import trace


logger = logging.getLogger(__name__)

_JPEG_MEDIA_TYPE = "image/jpeg"
_CACHE_FORMAT_VERSION = 1
# Reject unusable native canvases before Pillow allocates them. JPEG dimensions
# must fit its encoder; the pixel budget matches Pillow's source-image warning
# threshold (and remains enforced if source-image checks are disabled).
_MAX_CROP_DIMENSION: int = 65_500
_MAX_CROP_PIXELS: int = 89_478_485

# Keep strong references to best-effort writes until they finish.
_background_cache_writes: set[asyncio.Task[None]] = set()

# Documented keypoint order: left_eye, right_eye, nose, left_mouth_corner,
# right_mouth_corner (see people-gator-data-models instructions).
_REQUIRED_KEYPOINT_TYPES = (
    FaceKeypointType.left_eye,
    FaceKeypointType.right_eye,
    FaceKeypointType.nose,
    FaceKeypointType.left_mouth_corner,
    FaceKeypointType.right_mouth_corner,
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
    cache_hit: bool


def _cache_key(
    crop_cfg: AlignedFaceCropSettings,
    user_id: uuid.UUID,
    face: FaceResponse,
    keypoints: NDArray[np.float64],
    max_width: int | None,
) -> str:
    """Return a content-addressed key for all inputs that affect the crop."""
    fingerprint_input = {
        "version": _CACHE_FORMAT_VERSION,
        "source_id": str(face.source_id),
        "keypoints": keypoints.tolist(),
        "reference_width": crop_cfg.reference_width,
        "reference_height": crop_cfg.reference_height,
        "jpeg_quality": crop_cfg.jpeg_quality,
        "max_width": max_width,
    }
    serialized = json.dumps(
        fingerprint_input,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    fingerprint = hashlib.sha256(serialized).hexdigest()
    width_key = "original" if max_width is None else str(max_width)
    return posixpath.join(
        crop_cfg.cache_key_prefix.strip("/"),
        str(user_id),
        str(face.detection_id),
        width_key,
        f"{fingerprint}.jpg",
    )


def _is_missing_object(exc: ClientError | FileNotFoundError) -> bool:
    if isinstance(exc, FileNotFoundError):
        return True
    code = exc.response.get("Error", {}).get("Code")
    return code in {"404", "NoSuchKey", "NotFound"}


async def _read_cache(key: str) -> bytes | None:
    """Return cached crop bytes, treating cache errors as misses."""
    try:
        return await read_bytes(key)
    except (ClientError, FileNotFoundError) as exc:
        if not _is_missing_object(exc):
            logger.warning("aligned face crop cache read failed", extra={"key": key})
        return None
    except (BotoCoreError, OSError):
        logger.warning("aligned face crop cache read failed", extra={"key": key})
        return None


async def _write_cache(key: str, data: bytes) -> None:
    """Store crop bytes without allowing cache failures to fail the request."""
    try:
        await write_bytes(key, data)
    except (ClientError, BotoCoreError, OSError):
        logger.warning("aligned face crop cache write failed", extra={"key": key})


def _schedule_cache_write(key: str, data: bytes) -> None:
    task = asyncio.create_task(_write_cache(key, data))
    _background_cache_writes.add(task)
    task.add_done_callback(_background_cache_writes.discard)


def _reference_keypoints(crop_cfg: AlignedFaceCropSettings) -> NDArray[np.float64]:
    """Scale the 112x112 ArcFace template to the configured reference size."""
    scale = np.array(
        [
            crop_cfg.reference_width / 112.0,
            crop_cfg.reference_height / 112.0,
        ],
        dtype=np.float64,
    )
    return _ARCFACE_REFERENCE_112 * scale


def _ordered_keypoints(keypoints: list[Keypoint[FaceKeypointType]]) -> NDArray[np.float64]:
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


def _similarity_transform(
    src: NDArray[np.float64], dst: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64], float]:
    """Least-squares similarity transform (Umeyama) with ``dst ~= scale * R @ src + t``."""
    point_count: int = src.shape[0]
    src_mean: NDArray[np.float64] = src.mean(axis=0)
    dst_mean: NDArray[np.float64] = dst.mean(axis=0)
    src_centered: NDArray[np.float64] = src - src_mean
    dst_centered: NDArray[np.float64] = dst - dst_mean
    # There is no absolute pixel-distance epsilon: small valid faces still
    # align. Zero variance, including underflow to zero, has no usable scale.
    src_variance: np.float64 = src_centered.var(axis=0).sum()
    if not np.isfinite(src_variance) or src_variance <= 0:
        raise _invalid_keypoints()
    covariance: NDArray[np.float64] = (dst_centered.T @ src_centered) / point_count
    u: NDArray[np.float64]
    singular_values: NDArray[np.float64]
    vt: NDArray[np.float64]
    u, singular_values, vt = np.linalg.svd(covariance)
    sign_fix: NDArray[np.float64] = np.ones(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        sign_fix[-1] = -1
    rotation: NDArray[np.float64] = u @ np.diag(sign_fix) @ vt
    scale: float = float((singular_values * sign_fix).sum() / src_variance)
    if not math.isfinite(scale) or scale <= 0:
        raise _invalid_keypoints()
    translation: NDArray[np.float64] = dst_mean - scale * (rotation @ src_mean)
    return rotation, translation, scale


def _invalid_keypoints() -> SourceResolutionError:
    return SourceResolutionError(
        "face keypoints cannot produce a usable alignment",
        status_code=422,
        code="invalid_face_keypoints",
    )


def _crop_geometry(
    keypoints: NDArray[np.float64],
    crop_cfg: AlignedFaceCropSettings,
) -> tuple[tuple[int, int], tuple[float, ...]]:
    """Validate all geometry before division, integer conversion or allocation.

    Only numerical alignment failures are translated; image/storage failures
    retain their existing handling outside this calculation.
    """
    if not np.isfinite(keypoints).all():
        raise _invalid_keypoints()
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
            reference: NDArray[np.float64] = _reference_keypoints(crop_cfg)
            rotation: NDArray[np.float64]
            transform_translation: NDArray[np.float64]
            scale: float
            rotation, transform_translation, scale = _similarity_transform(keypoints, reference)
            if (
                not math.isfinite(scale)
                or scale <= 0
                or not np.isfinite(rotation).all()
                or not np.isfinite(transform_translation).all()
            ):
                raise _invalid_keypoints()
            scale_factor: float = 1.0 / scale
            if not math.isfinite(scale_factor) or scale_factor <= 0:
                raise _invalid_keypoints()
            dimensions: NDArray[np.float64] = np.array(
                [crop_cfg.reference_width, crop_cfg.reference_height]
            ) * scale_factor
            if (
                not np.isfinite(dimensions).all()
                or (dimensions <= 0).any()
                or (dimensions > _MAX_CROP_DIMENSION).any()
            ):
                raise _invalid_keypoints()
            output_width: int
            output_height: int
            output_width, output_height = (max(1, round(float(value))) for value in dimensions)
            if output_width * output_height > _MAX_CROP_PIXELS:
                raise _invalid_keypoints()
            scaled_reference: NDArray[np.float64] = reference * scale_factor
            translation: NDArray[np.float64] = (
                scaled_reference.mean(axis=0) - (rotation @ keypoints.mean(axis=0))
            )
            inverse_rotation: NDArray[np.float64] = rotation.T
            inverse_translation: NDArray[np.float64] = -inverse_rotation @ translation
            if not np.isfinite(inverse_translation).all():
                raise _invalid_keypoints()
    except (FloatingPointError, np.linalg.LinAlgError) as exc:
        raise _invalid_keypoints() from exc
    coefficients: tuple[float, float, float, float, float, float] = (
        float(inverse_rotation[0, 0]),
        float(inverse_rotation[0, 1]),
        float(inverse_translation[0]),
        float(inverse_rotation[1, 0]),
        float(inverse_rotation[1, 1]),
        float(inverse_translation[1]),
    )
    return (output_width, output_height), coefficients


def _render_aligned_crop(
    image_bytes: bytes,
    keypoints: NDArray[np.float64],
    crop_cfg: AlignedFaceCropSettings,
    max_width: int | None,
) -> bytes:
    """Warp ``image_bytes`` so ``keypoints`` align to the ArcFace template.

    Only rotation and translation are applied (scale fixed to 1) so the
    output preserves the original image's pixel scale; the output canvas is
    sized to match, then optionally downscaled to ``max_width``.
    """
    output_size, affine_coefficients = _crop_geometry(keypoints, crop_cfg)

    with Image.open(io.BytesIO(image_bytes)) as source_image:
        if source_image.mode not in ("RGB", "L"):
            source_image = source_image.convert("RGB")
        aligned: Image.Image = source_image.transform(
            output_size,
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
    source: GenericSourceResponse,
) -> bytes:
    """Fetch the full-resolution bytes of the image a face was detected in."""
    if source.source_type == SourceKind.image:
        content, _media_type = await get_image_content(str(source.url))
        return content
    if (
        source.source_type == SourceKind.page
        and source.library is not None
        and source.document_id is not None
        and source.page_id is not None
    ):
        page_image = await get_page_image(
            source.library,
            source.document_id,
            source.page_id,
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
    user_id: uuid.UUID,
    face: FaceResponse,
    source: GenericSourceResponse,
    *,
    max_width: int | None = None,
) -> AlignedFaceCropContent:
    """Render a crop from resolved metadata and object storage only."""
    if source.source_id != face.source_id:
        raise SourceResolutionError(
            "Face source does not match the supplied source",
            status_code=422,
            code="source_mismatch",
        )
    crop_cfg = settings.aligned_face_crop
    if max_width is not None and max_width > crop_cfg.max_output_width:
        raise SourceResolutionError(
            "requested max_width exceeds the configured limit",
            status_code=422,
            code="invalid_max_width",
        )
    keypoints = _ordered_keypoints(face.keypoints)
    cache_key: str | None = None
    if crop_cfg.cache_enabled:
        cache_key = _cache_key(crop_cfg, user_id, face, keypoints, max_width)
        cached = await _read_cache(cache_key)
        if cached is not None:
            return AlignedFaceCropContent(
                content=cached,
                media_type=_JPEG_MEDIA_TYPE,
                cache_hit=True,
            )

    image_bytes = await _read_face_source_image(source)
    content = await asyncio.to_thread(
        _render_aligned_crop, image_bytes, keypoints, crop_cfg, max_width
    )
    if cache_key is not None:
        _schedule_cache_write(cache_key, content)
    return AlignedFaceCropContent(
        content=content,
        media_type=_JPEG_MEDIA_TYPE,
        cache_hit=False,
    )
