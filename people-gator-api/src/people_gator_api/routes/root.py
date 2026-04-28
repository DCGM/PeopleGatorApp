from fastapi import APIRouter
from structlog import get_logger, BoundLogger
from people_gator_api.schemas import HelloWorldResponse

logger: BoundLogger = get_logger(__name__)

router = APIRouter()

@router.get("/api/v1/")
async def home() -> HelloWorldResponse:
    var = "Hello from people-gator-api!"
    logger.info("Root endpoint called", message=var, version="0.1.0", package_name="people-gator-api", endpoint="/api/v1/")
    return HelloWorldResponse(message=var)
