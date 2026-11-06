from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from people_gator_api.services.embedding_service.http_service import (
    close_embedding_service,
    init_embedding_service,
)
from people_gator_api.services.openrouter_service import (
    close_openrouter_service,
    init_openrouter_service,
)
from people_gator_api.utils.opentelemetry import initialize_opentelemetry
from people_gator_api.utils.logging import configure_logging
from people_gator_api.settings import settings
from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.services.database_service import (
    close_db,
    init_db,
)
from people_gator_api.utils.version_info import get_version_info
from people_gator_api.utils.swagger import swagger_html
import dotenv

dotenv.load_dotenv()  # Load environment variables from .env file at startup


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await init_db()
        await init_embedding_service()
        await init_openrouter_service()
        yield
    finally:
        await close_embedding_service()
        await close_openrouter_service()
        await close_db()


def get_app() -> FastAPI:
    app = FastAPI(
        title="People Gator API",
        description="An API for managing people and their relationships through backend-neutral persistence contracts.",
        version=get_version_info().full_version,
        lifespan=lifespan,
        docs_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors.allow_origins,
        allow_origin_regex=settings.cors.allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.otel.enabled:
        (
            fastapi_instrumentor,
            _,
            _,
        ) = initialize_opentelemetry()
        fastapi_instrumentor.instrument_app(app)
        configure_logging()
    else:
        configure_logging()
    @app.get("/docs", include_in_schema=False)
    async def docs(request: Request):
        root_path = request.scope.get("root_path", "").rstrip("/")
        return swagger_html(openapi_url=f"{root_path}{app.openapi_url}", title=f"{app.title} - Swagger UI")

    app.include_router(v1_router)
    def openapi():
        if app.openapi_schema is None:
            schema = get_openapi(title=app.title, version=app.version,
                                 description=app.description, routes=app.routes)
            for path in schema.get("paths", {}).values():
                for operation in path.values():
                    if isinstance(operation, dict):
                        for requirement in operation.get("security", []):
                            if "PeopleGatorAPIKey" in requirement:
                                requirement["PeopleGatorAPIKey"] = []
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = openapi
    return app


app = get_app()
