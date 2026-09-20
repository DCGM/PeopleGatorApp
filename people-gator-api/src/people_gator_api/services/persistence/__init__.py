"""Backend-neutral persistence contracts and adapters."""

from people_gator_api.services.persistence.contracts import (
    Database,
    EntityListQuery,
    EntityPatchCommand,
    EntityRepository,
    FaceListQuery,
    FacePatchCommand,
    FaceRepository,
    SourceListQuery,
    SourceLookup,
    SourceRepository,
    TextMentionListQuery,
    TextMentionPatchCommand,
    TextMentionRepository,
    UserListQuery,
    UserPatchCommand,
    UserRepository,
    WriteContext,
)
from people_gator_api.services.persistence.postgres import postgres_database
from people_gator_api.services.persistence.weaviate import weaviate_database

__all__ = [
    "Database",
    "EntityListQuery",
    "EntityPatchCommand",
    "EntityRepository",
    "FaceListQuery",
    "FacePatchCommand",
    "FaceRepository",
    "SourceListQuery",
    "SourceLookup",
    "SourceRepository",
    "TextMentionListQuery",
    "TextMentionPatchCommand",
    "TextMentionRepository",
    "UserListQuery",
    "UserPatchCommand",
    "UserRepository",
    "WriteContext",
    "postgres_database",
    "weaviate_database",
]
