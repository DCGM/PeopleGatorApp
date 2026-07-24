"""Weaviate async client lifecycle management."""

import logging

import weaviate
from weaviate import WeaviateAsyncClient
from weaviate.classes.init import Auth

from people_gator_api.settings import settings
from people_gator_api.services.vector_service.schema import ALL_COLLECTION_SPECS

logger = logging.getLogger(__name__)

_client: WeaviateAsyncClient | None = None


def _build_client() -> WeaviateAsyncClient:
    cfg = settings.weaviate
    auth = Auth.api_key(cfg.api_key) if cfg.api_key else None
    return weaviate.use_async_with_custom(
        http_host=cfg.http_host,
        http_port=cfg.http_port,
        http_secure=cfg.http_secure,
        grpc_host=cfg.grpc_host,
        grpc_port=cfg.grpc_port,
        grpc_secure=cfg.grpc_secure,
        auth_credentials=auth,
    )


async def init_weaviate() -> None:
    """Connect the async Weaviate client and ensure collection schemas exist.

    Call once during application startup (e.g. from FastAPI lifespan).
    """
    global _client  # noqa: PLW0603
    _client = _build_client()
    await _client.connect()
    logger.info(
        "Weaviate client connected",
        extra={
            "http_host": settings.weaviate.http_host,
            "http_port": settings.weaviate.http_port,
        },
    )
    await _ensure_collections(_client)


async def close_weaviate() -> None:
    """Close the async Weaviate client.

    Call once during application shutdown (e.g. from FastAPI lifespan).
    """
    global _client  # noqa: PLW0603
    if _client is not None:
        await _client.close()
        _client = None
        logger.info("Weaviate client closed")


def get_weaviate_client() -> WeaviateAsyncClient:
    """Return the connected WeaviateAsyncClient.

    Raises RuntimeError if :func:`init_weaviate` has not been called.
    """
    if _client is None:
        raise RuntimeError(
            "Weaviate client is not initialised.  "
            + "Ensure init_weaviate() has been awaited during startup."
        )
    return _client


# ---------------------------------------------------------------------------
# Idempotent schema bootstrap
# ---------------------------------------------------------------------------


async def _ensure_collections(client: WeaviateAsyncClient) -> None:
    """Create Weaviate collections if they do not already exist."""

    for collection_name, (properties, references, vector_config) in ALL_COLLECTION_SPECS.items():
        if await client.collections.exists(collection_name):
            logger.debug("Collection %s already exists", collection_name)
            continue

        if vector_config is not None:
            await client.collections.create(
                name=collection_name,
                description="Canonical People Gator persistence collection.",
                properties=properties,
                references=references,  # pyright: ignore[reportArgumentType] - Weaviate expects these concrete configs at runtime but types them against invariant private base classes.
                vector_config=vector_config,  # pyright: ignore[reportArgumentType] - Weaviate expects these concrete configs at runtime but types them against invariant private base classes.
            )
        else:
            await client.collections.create(
                name=collection_name,
                description="Canonical People Gator persistence collection.",
                properties=properties,
                references=references,  # pyright: ignore[reportArgumentType] - Weaviate expects these concrete configs at runtime but types them against invariant private base classes.
            )
        logger.info("Created Weaviate collection: %s", collection_name)
