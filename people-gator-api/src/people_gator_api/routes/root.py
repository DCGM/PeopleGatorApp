from fastapi import APIRouter
from logging import getLogger, Logger
from people_gator_api.schemas import HelloWorldResponse

logger: Logger = getLogger(__name__)

router = APIRouter()

@router.get("/api/v1/")
async def home() -> HelloWorldResponse:
    response = HelloWorldResponse(message="Hello from people-gator-api!")
    logger.info("Root endpoint called", extra={"model": response.model_dump()})
    return response
