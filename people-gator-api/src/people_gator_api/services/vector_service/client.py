"""Weaviate async client lifecycle management.

Follows the same module-level singleton pattern as storage/s3.py:

    await init_weaviate()          # at application startup
    client = get_weaviate_client() # during request handling
    await close_weaviate()         # at application shutdown

The client is built from WeaviateSettings and uses the custom-endpoint
helper so that the connection target is fully configurable via environment
variables without any hard-coded defaults in application code.
"""

import logging
from typing import Any, cast

import weaviate
from weaviate import WeaviateAsyncClient
from weaviate.classes.init import Auth

from people_gator_api.settings import settings
from people_gator_api.services.vector_service.schema import (
    ANNOTATION_COLLECTION_SPECS,
    ENTITY_COLLECTION,
    ENTITY_PROPERTIES,
    ENTITY_SNAPSHOT_COLLECTION,
    ENTITY_SNAPSHOT_PROPERTIES,
    entity_named_vector_configs,
    entity_snapshot_named_vector_configs,
)

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
    """Create Weaviate collections if they do not already exist.

    This function is idempotent — calling it repeatedly is safe.  It uses
    ``client.collections.exists()`` to avoid the overhead of recreating
    or patching schemas on every application restart.
    """
    await _ensure_annotation_collections(client)
    await _ensure_entity_snapshot(client)
    await _ensure_entity_collection(client)


async def _ensure_annotation_collections(client: WeaviateAsyncClient) -> None:
    for collection_name, (properties, vector_config) in ANNOTATION_COLLECTION_SPECS.items():
        if await client.collections.exists(collection_name):
            logger.debug("Collection %s already exists", collection_name)
            continue

        await client.collections.create(
            name=collection_name,
            description=(
                "Relational annotation mirror collection with filterable metadata "
                "and caller-supplied vectors for nearest-neighbour search."
            ),
            properties=properties,
            vector_config=cast(Any, vector_config),
        )
        logger.info("Created Weaviate collection: %s", collection_name)


async def _ensure_entity_snapshot(client: WeaviateAsyncClient) -> None:
    if await client.collections.exists(ENTITY_SNAPSHOT_COLLECTION):
        logger.debug("Collection %s already exists", ENTITY_SNAPSHOT_COLLECTION)
        return

    await client.collections.create(
        name=ENTITY_SNAPSHOT_COLLECTION,
        description=(
            "One document per entity, updated on every LINK_CONSENSUS sync.  "
            "Stores named vectors per modality (face centroid, name centroid) "
            "to enable weighted multi-modal entity similarity search."
        ),
        properties=ENTITY_SNAPSHOT_PROPERTIES,
        vector_config=entity_snapshot_named_vector_configs(),
    )
    logger.info("Created Weaviate collection: %s", ENTITY_SNAPSHOT_COLLECTION)


async def _ensure_entity_collection(client: WeaviateAsyncClient) -> None:
    if await client.collections.exists(ENTITY_COLLECTION):
        logger.debug("Collection %s already exists", ENTITY_COLLECTION)
        return

    await client.collections.create(
        name=ENTITY_COLLECTION,
        description=(
            "Entity-level searchable aggregate with normalized name and description "
            "plus named vectors for name and description similarity."
        ),
        properties=ENTITY_PROPERTIES,
        vector_config=cast(Any, entity_named_vector_configs()),
    )
    logger.info("Created Weaviate collection: %s", ENTITY_COLLECTION)
