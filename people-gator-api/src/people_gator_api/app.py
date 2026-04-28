from fastapi import FastAPI
from people_gator_api.utils.opentelemetry import initialize_opentelemetry
from people_gator_api.utils.logging import configure_logging
from people_gator_api.utils.settings import settings
from people_gator_api.routes import root_router

app = FastAPI(
    title="People Gator API",
    description="An API for managing people and their relationships, powered by Weaviate, SQLAlchemy and OpenTelemetry.",
    version="0.1.0",
)

if settings.otel.enabled:
    (
        _, _, _,
        logging_handler,
        fastapi_instrumentor,
        _, _, _, _,
    ) = initialize_opentelemetry()    
    fastapi_instrumentor.instrument_app(app)
    configure_logging(logging_handler)  # Initialize structlog with OpenTelemetry integration
else:
    configure_logging()  # Initialize structlog without OpenTelemetry integration

app.include_router(root_router)
