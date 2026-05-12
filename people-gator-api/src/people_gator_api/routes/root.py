from fastapi import APIRouter
from structlog import get_logger, BoundLogger
from people_gator_api.schemas import HelloWorldResponse

logger: BoundLogger = get_logger(__name__)

router = APIRouter()

@router.get("/api/v1/")
async def home() -> HelloWorldResponse:
    response = HelloWorldResponse(message="Hello from people-gator-api!")
    logger.info("Root endpoint called", **response.model_dump())
    return response
