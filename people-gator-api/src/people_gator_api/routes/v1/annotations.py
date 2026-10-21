"""Face annotation endpoints backed by the persistence contracts."""

import uuid

from fastapi import APIRouter, Query, Response, status

from people_gator_api.media.aligned_face_crop import get_aligned_face_crop
from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FaceListRequest,
    FaceListResponse,
    FacePatchRequest,
    FaceResponse,
    FacesBatchCreateRequest,
    FacesBatchPatchRequest,
)
from people_gator_api.schemas.sources import GenericSourceLookupRequest
from people_gator_api.routes.v1.query_dependencies import (
    DEFAULT_SORT,
    FaceListFilterDependency,
    FaceListSortDependency,
    ListRequestDependency,
)
from people_gator_api.services.auth_service import (
    AdminActorDependency,
    AnnotatorActorDependency,
    BrowseActorDependency,
    DataIngestActorDependency,
)
from people_gator_api.services.database_service import (
    DatabaseDependency,
)
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["annotations"])


@router.get("/faces", response_model=FaceListResponse)
async def list_faces_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    filter: FaceListFilterDependency,
    list_request: ListRequestDependency,
    sort: FaceListSortDependency = DEFAULT_SORT,
) -> FaceListResponse:
    del user
    try:
        return await database.faces.list(
            FaceListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
                sort=sort.sort,
                sort_direction=sort.sort_direction,
            )
        )
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.post("/faces", response_model=FaceResponse, status_code=status.HTTP_201_CREATED)
async def create_face_route(
    payload: FaceCreateRequest,
    database: DatabaseDependency,
    user: DataIngestActorDependency,
) -> FaceResponse:
    try:
        return await database.faces.create(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.post(
    "/faces:batch",
    response_model=list[FaceResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_face_batch_route(
    payload: FacesBatchCreateRequest,
    database: DatabaseDependency,
    user: DataIngestActorDependency,
) -> list[FaceResponse]:
    try:
        return await database.faces.create_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.patch("/faces:batch", response_model=list[FaceResponse | None])
async def patch_face_batch_route(
    payload: FacesBatchPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> list[FaceResponse | None]:
    try:
        return await database.faces.patch_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))


@router.delete("/faces:batch", response_model=int)
async def delete_face_batch_route(
    detection_id: list[uuid.UUID],
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> int:
    return await database.faces.delete_batch(detection_id, context=user)


@router.get("/faces/{detection_id}/aligned_crop", response_class=Response)
async def get_face_aligned_crop_route(
    detection_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseActorDependency,
    max_width: int | None = Query(default=None, gt=0),
) -> Response:
    """Return one ArcFace-aligned face crop, kept at the original image scale."""
    face = await database.faces.get(detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    source = await database.sources.lookup(
        GenericSourceLookupRequest(source_id=face.source_id)
    )
    if source is None:
        raise_api_error(404, "not_found", "Face source not found")
    try:
        crop = await get_aligned_face_crop(
            user.user_id,
            face,
            source,
            max_width=max_width,
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
    database: DatabaseDependency,
    user: BrowseActorDependency,
) -> FaceResponse:
    del user
    face = await database.faces.get(detection_id)
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.patch("/faces/{detection_id}", response_model=FaceResponse)
async def patch_face_route(
    detection_id: uuid.UUID,
    payload: FacePatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> FaceResponse:
    try:
        face = await database.faces.patch(detection_id, payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    if face is None:
        raise_api_error(404, "not_found", "Face not found")
    return face


@router.delete("/faces/{detection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_face_route(
    detection_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> None:
    if not await database.faces.delete(detection_id, context=user):
        raise_api_error(404, "not_found", "Face not found")
