from fastapi import APIRouter
from logging import getLogger, Logger
from people_gator_api.schemas.root import RootResponse

logger: Logger = getLogger(__name__)

router = APIRouter()

@router.get("/api/v1/")
async def home() -> RootResponse:
    response = RootResponse(message="Hello from people-gator-api!")
    logger.info("Root endpoint called", extra={"model": response.model_dump()})
    return response
