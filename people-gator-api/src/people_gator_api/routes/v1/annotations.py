"""Face annotation endpoints."""

import uuid
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Query, Response, status

from people_gator_api.schemas.entities import (
    FaceCreateRequest,
    FaceEmbeddingBatchUpdateResponse,
    FaceEmbeddingUpdateRequest,
    FaceEntityPatchRequest,
    FaceListResponse,
    FaceResponse,
)
from people_gator_api.services.auth_service import (
    AnnotatorUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.crud_services.aligned_face_crop_service import (
    get_aligned_face_crop,
)
from people_gator_api.services.crud_services.annotation_service import (
    create_face,
    create_face_batch,
    get_face,
    list_faces,
    patch_face_entity,
    update_face_embedding_batch,
)
from people_gator_api.services.crud_services.source_service import SourceResolutionError
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["annotations"])


async def _iter_payloads[T](items: list[T]) -> AsyncGenerator[T, None]:
    for item in items:
        yield item


@router.get("/faces", response_model=FaceListResponse)
async def list_faces_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    source_id: uuid.UUID | None = None,
    entity_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> FaceListResponse:
    return await list_faces(
        session,
        user.user_id,
        source_id,
        entity_id,
        after_id,
        limit,
        owner_user_id=user_id,
    )


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> FaceResponse:
    try:
        face = await create_face(session, payload, user.user_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return face


@router.post(
    "/faces:batch",
    response_model=list[FaceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_face_batch_route(
    payload: list[FaceCreateRequest],
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> list[FaceResponse]:
    try:
        faces = await create_face_batch(
            session,
            _iter_payloads(payload),
            user.user_id,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return faces


@router.post("/faces:embeddings", response_model=FaceEmbeddingBatchUpdateResponse)
async def update_face_embedding_batch_route(
    payload: list[FaceEmbeddingUpdateRequest],
    session: WeaviateSessionDependency,
    _user: DataIngestUserDependency,
) -> FaceEmbeddingBatchUpdateResponse:
    updated_count = await update_face_embedding_batch(session, payload)
    return FaceEmbeddingBatchUpdateResponse(updated_count=updated_count)


@router.get("/faces/{detection_id}/aligned_crop", response_class=Response)
async def get_face_aligned_crop_route(
    detection_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    max_width: int | None = Query(default=None, gt=0),
) -> Response:
    """Return one ArcFace-aligned face crop, kept at the original image scale."""
    try:
        crop = await get_aligned_face_crop(
            session, user.user_id, detection_id, max_width=max_width
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(
        content=crop.content,
        media_type=crop.media_type,
        headers={"X-Cache": "HIT" if crop.cache_hit else "MISS"},
    )


@router.get("/faces/{detection_id}", response_model=FaceResponse)
async def get_face_route(
    detection_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> FaceResponse:
    face = await get_face(session, user.user_id, detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.patch("/faces/{detection_id}", response_model=FaceResponse)
async def patch_face_entity_route(
    detection_id: uuid.UUID,
    payload: FaceEntityPatchRequest,
    session: WeaviateSessionDependency,
    user: AnnotatorUserDependency,
) -> FaceResponse:
    face = await patch_face_entity(
        session,
        user.user_id,
        detection_id,
        payload.entity_id,
    )
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face
