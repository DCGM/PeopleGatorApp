from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
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
from people_gator_api.routes.jwks import router as jwks_router
from people_gator_api.services.database_service import (
    close_postgres,
    init_postgres,
)
import dotenv

dotenv.load_dotenv()  # Load environment variables from .env file at startup


async def well_known_cors(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    if not request.url.path.startswith("/.well-known/"):
        return await call_next(request)

    if request.method == "OPTIONS":
        response = Response(status_code=204)
    else:
        response = await call_next(request)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, HEAD, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Max-Age"] = "86400"
    return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_embedding_service()
    await init_openrouter_service()
    await init_postgres()
    yield
    await close_embedding_service()
    await close_openrouter_service()
    await close_postgres()


def get_app() -> FastAPI:
    app = FastAPI(
        title="People Gator API",
        description="An API for managing people and their relationships through backend-neutral persistence contracts.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.cors.allow_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(BaseHTTPMiddleware, dispatch=well_known_cors)

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
    app.include_router(v1_router)
    app.include_router(jwks_router)
    return app


app = get_app()
