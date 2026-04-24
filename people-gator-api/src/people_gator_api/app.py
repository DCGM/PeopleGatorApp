from fastapi import FastAPI
from people_gator_api.utils.opentelemetry import initialize_opentelemetry
from people_gator_api.utils.logging import configure_logging
import structlog

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
configure_logging(logging_handler)  # Initialize structlog with OpenTelemetry integration

app = FastAPI()
fastapi_instrumentor.instrument_app(app)

main_logger: structlog.BoundLogger = structlog.get_logger(__name__)

@app.get("/")
async def read_root():
    var = "Hello from people-gator-api!"
    main_logger.info("Root endpoint called", var=var)
    return {"message": var}
