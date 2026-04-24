from fastapi import FastAPI
from people_gator_api.utils.opentelemetry import initialize_opentelemetry
from people_gator_api.utils.logging import configure_logging
from people_gator_api.utils.settings import settings
import structlog

app = FastAPI()

if settings.otel.enabled:
    (
        _,
        _,
        _,
        logging_handler,
        fastapi_instrumentor,
        _,
        _,
        _,
        _,
    ) = initialize_opentelemetry()    
    fastapi_instrumentor.instrument_app(app)
    configure_logging(logging_handler)  # Initialize structlog with OpenTelemetry integration
else:
    configure_logging()  # Initialize structlog without OpenTelemetry integration

logger: structlog.BoundLogger = structlog.get_logger(__name__)

@app.get("/")
async def read_root():
    var = "Hello from people-gator-api!"
    logger.info("Root endpoint called", var=var)
    return {"message": var}
