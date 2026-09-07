from fastapi import APIRouter
from logging import (
    getLogger,
    Logger,
)
from people_gator_api.schemas.root import HealthResponse, RootResponse

logger: Logger = getLogger(__name__)

router = APIRouter()


@router.get("/")
async def home() -> RootResponse:
    response = RootResponse(message="Hello from people-gator-api!")
    logger.info("Root endpoint called", extra={"model": response.model_dump()})
    return response


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
