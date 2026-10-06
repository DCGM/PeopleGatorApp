"""Weaviate client construction and collection schema management."""

import asyncio
import logging

import weaviate
from weaviate import WeaviateAsyncClient
from weaviate.classes.config import (
    Configure,
    Property,
    ReferenceProperty,
    VectorDistances,
)
from weaviate.classes.init import Auth

from people_gator_api.persistence.weaviate.schema import (
    ADDITIVE_PROPERTY_MIGRATIONS,
    ALL_COLLECTION_SPECS,
    CollectionSpec,
)
from people_gator_api.settings import settings

logger = logging.getLogger(__name__)


def _build_client() -> WeaviateAsyncClient:
    cfg = settings.persistence.weaviate
    if cfg is None:
        raise ValueError("Weaviate requires persistence.weaviate configuration")
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


def build_weaviate_client() -> WeaviateAsyncClient:
    """Build an unconnected client for standalone operational commands."""
    return _build_client()


# ---------------------------------------------------------------------------
# Idempotent schema bootstrap
# ---------------------------------------------------------------------------


async def ensure_collections(
    client: WeaviateAsyncClient,
    *,
    retry_delay_seconds: float = 2.0,
    max_retries: int = 3,
) -> None:
    """Create missing collections and apply declared additive schema migrations."""

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
                "Collection %s already exists",
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
                references=[reference for reference in references],
                vector_config=[
                    Configure.Vectors.self_provided(
                        name=vector.name,
                        vector_index_config=Configure.VectorIndex.hnsw(
                            distance_metric=VectorDistances.COSINE,
                        ),
                    )
                    for vector in vector_config
                ],
            )
        else:
            await client.collections.create(
                name=collection_name,
                description="Canonical People Gator persistence collection.",
                properties=properties,
                references=[reference for reference in references],
            )
        logger.info("Created Weaviate collection: %s", collection_name)

    for collection_name, properties in ADDITIVE_PROPERTY_MIGRATIONS.items():
        if not exists_by_collection.get(collection_name, False):
            continue
        await _add_missing_properties(client, collection_name, properties)


async def _add_missing_properties(
    client: WeaviateAsyncClient,
    collection_name: str,
    properties: list[Property],
) -> None:
    """Add explicitly migrated properties that are absent from a collection."""
    collection = client.collections.use(collection_name)
    config = await collection.config.get(simple=True)
    existing_property_names = {property_.name for property_ in config.properties}
    for property_ in properties:
        if property_.name in existing_property_names:
            continue
        await collection.config.add_property(property_)
        logger.info(
            "Added Weaviate property %s.%s",
            collection_name,
            property_.name,
        )


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
