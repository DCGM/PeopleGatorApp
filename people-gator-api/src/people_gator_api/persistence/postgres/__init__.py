from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.persistence.contracts import Database

from .entity_repository import PostgresEntityRepository
from .source_repository import PostgresSourceRepository
from .face_repository import PostgresFaceRepository
from .face_model_repository import PostgresFaceModelRepository
from .text_mention_repository import PostgresTextMentionRepository
from .user_repository import PostgresUserRepository
from .api_key_repository import PostgresAPIKeyRepository

def postgres_database(session: AsyncSession) -> Database:
    """Bind all repositories to one request-scoped SQLAlchemy session."""
    return Database(
        entities=PostgresEntityRepository(session),
        sources=PostgresSourceRepository(session),
        faces=PostgresFaceRepository(session),
        face_models=PostgresFaceModelRepository(session),
        text_mentions=PostgresTextMentionRepository(session),
        users=PostgresUserRepository(session),
        api_keys=PostgresAPIKeyRepository(session),
    )


__all__ = [
    "postgres_database",
]
