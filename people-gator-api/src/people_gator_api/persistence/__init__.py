"""Backend-neutral persistence contracts with lazily loaded adapters."""

from typing import TYPE_CHECKING, Any

from people_gator_api.persistence.contracts import (
    CreateResult,
    Database,
    EntityRepository,
    FaceModelRepository,
    FaceRepository,
    SourceRepository,
    TextMentionRepository,
    UserRepository,
)
from people_gator_api.schemas.common import GenericActor

if TYPE_CHECKING:
    from people_gator_api.persistence.postgres import postgres_database
    from people_gator_api.persistence.weaviate import weaviate_database


def __getattr__(name: str) -> Any:
    if name == "postgres_database":
        from people_gator_api.persistence.postgres import postgres_database

        return postgres_database
    if name == "weaviate_database":
        from people_gator_api.persistence.weaviate import weaviate_database

        return weaviate_database
    raise AttributeError(name)


__all__ = [
    "CreateResult",
    "Database",
    "EntityRepository",
    "FaceModelRepository",
    "FaceRepository",
    "SourceRepository",
    "TextMentionRepository",
    "UserRepository",
    "GenericActor",
    "postgres_database",
    "weaviate_database",
]
