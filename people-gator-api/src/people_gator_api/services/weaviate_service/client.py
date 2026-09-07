"""Weaviate async client lifecycle management."""

import asyncio
import logging
import time

import weaviate
from weaviate import WeaviateAsyncClient
from weaviate.classes.config import ReferenceProperty
from weaviate.classes.init import Auth

from people_gator_api.settings import settings
from people_gator_api.services.weaviate_service.db_schema import (
    ALL_COLLECTION_SPECS,
    CollectionSpec,
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
    if _client is not None:
        return

    cfg = settings.weaviate
    deadline = time.monotonic() + cfg.startup_timeout_seconds
    attempt = 0
    while True:
        attempt += 1
        candidate = _build_client()
        try:
            await candidate.connect()
            await _ensure_collections(candidate)
        except Exception as exc:
            # A failed connect can still allocate HTTP/gRPC resources. Close
            # the whole candidate and build a fresh client for the next try.
            await candidate.close()
            remaining_seconds = deadline - time.monotonic()
            if remaining_seconds <= 0:
                logger.error(
                    "Unable to initialise Weaviate within %.1f seconds",
                    cfg.startup_timeout_seconds,
                )
                raise
            delay_seconds = min(
                cfg.startup_retry_interval_seconds,
                remaining_seconds,
            )
            logger.warning(
                "Weaviate is not ready (attempt %s); retrying in %.1f seconds: %s",
                attempt,
                delay_seconds,
                exc,
            )
            await asyncio.sleep(delay_seconds)
            continue

        _client = candidate
        logger.info(
            "Weaviate client connected and schema is ready",
            extra={
                "http_host": cfg.http_host,
                "http_port": cfg.http_port,
                "attempt": attempt,
            },
        )
        return


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


async def _ensure_collections(
    client: WeaviateAsyncClient,
    *,
    retry_delay_seconds: float = 2.0,
    max_retries: int = 3,
) -> None:
    """Create missing Weaviate collections without mutating existing schemas.

    Startup intentionally performs existence checks and creates only missing
    collections. Schema migration or drift reconciliation must be handled by
    dedicated tooling outside this lifecycle path.
    """

    ordered_specs = ordered_collection_specs(ALL_COLLECTION_SPECS)
    exists_by_collection: dict[str, bool] = {}

    for collection_name, _ in ordered_specs:
        exists = await _collection_exists_with_retry(
            client=client,
            collection_name=collection_name,
            retry_delay_seconds=retry_delay_seconds,
            max_retries=max_retries,
        )
        exists_by_collection[collection_name] = exists
        if exists:
            logger.debug(
                "Collection %s already exists; leaving schema unchanged",
                collection_name,
            )

    for collection_name, (
        properties,
        references,
        vector_config,
    ) in ordered_specs:
        if exists_by_collection[collection_name]:
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


async def _collection_exists_with_retry(
    *,
    client: WeaviateAsyncClient,
    collection_name: str,
    retry_delay_seconds: float,
    max_retries: int,
) -> bool:
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await client.collections.exists(collection_name)
        except Exception as exc:  # pragma: no cover - exercised via runtime failures
            last_error = exc
            if attempt >= max_retries:
                logger.warning(
                    "Unable to confirm Weaviate collection %s after %s attempts: %s",
                    collection_name,
                    max_retries + 1,
                    exc,
                )
                raise
            logger.warning(
                "Transient Weaviate error while checking collection %s (attempt %s/%s): %s",
                collection_name,
                attempt + 1,
                max_retries + 1,
                exc,
            )
            await asyncio.sleep(retry_delay_seconds)

    if last_error is not None:
        raise last_error
    return False


def ordered_collection_specs(
    collection_specs: dict[str, CollectionSpec],
) -> list[tuple[str, CollectionSpec]]:
    dependencies = {
        collection_name: _collection_dependencies(collection_name, collection_specs)
        for collection_name in collection_specs
    }
    remaining_specs = dict(collection_specs)
    resolved_collections: set[str] = set()
    ordered_specs: list[tuple[str, CollectionSpec]] = []

    while remaining_specs:
        ready_collections = [
            collection_name
            for collection_name in remaining_specs
            if dependencies[collection_name] <= resolved_collections
        ]
        if not ready_collections:
            unresolved_collections = ", ".join(sorted(remaining_specs))
            raise ValueError(
                "Weaviate collection specs contain unresolved reference dependencies: "
                + unresolved_collections
            )
        for collection_name in ready_collections:
            ordered_specs.append(
                (collection_name, remaining_specs.pop(collection_name))
            )
            resolved_collections.add(collection_name)

    return ordered_specs


def _collection_dependencies(
    collection_name: str,
    collection_specs: dict[str, CollectionSpec],
) -> set[str]:
    _, references, _ = collection_specs[collection_name]
    return {
        target_collection
        for target_collection in _reference_targets(references)
        if target_collection in collection_specs
        and target_collection != collection_name
    }


def _reference_targets(references: list[ReferenceProperty]) -> set[str]:
    return {reference.target_collection for reference in references}
