"""Administrative face embedding model registry endpoints."""

from fastapi import APIRouter, status

from people_gator_api.schemas.face_models import (
    FaceModelListResponse,
    FaceModelRegisterRequest,
    FaceModelResponse,
)
from people_gator_api.services.auth_service import AdminActorDependency, BrowseActorDependency
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error


router = APIRouter(tags=["face models"])


@router.post(
    "/face-models",
    response_model=FaceModelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_face_model_route(
    payload: FaceModelRegisterRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> FaceModelResponse:
    del user
    try:
        return await database.face_models.register(payload)
    except ValueError as exc:
        raise_api_error(409, "face_model_conflict", str(exc))


@router.get("/face-models", response_model=FaceModelListResponse)
async def list_face_models_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
) -> FaceModelListResponse:
    del user
    return await database.face_models.list()


__all__ = ["router"]
