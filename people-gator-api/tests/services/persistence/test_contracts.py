import inspect

from people_gator_api.services.persistence.contracts import (
    EntityRepository,
    FaceRepository,
    SourceRepository,
    TextMentionRepository,
    UserRepository,
)
from people_gator_api.services.persistence.postgres import (
    PostgresEntityRepository,
    PostgresFaceRepository,
    PostgresSourceRepository,
    PostgresTextMentionRepository,
    PostgresUserRepository,
)
from people_gator_api.services.persistence.weaviate import (
    WeaviateEntityRepository,
    WeaviateFaceRepository,
    WeaviateSourceRepository,
    WeaviateTextMentionRepository,
    WeaviateUserRepository,
)


def test_batch_writes_are_required_backend_operations() -> None:
    assert "import_batch" in EntityRepository.__abstractmethods__
    assert "patch_batch" in EntityRepository.__abstractmethods__
    assert "update_embeddings_batch" in EntityRepository.__abstractmethods__
    assert "delete_batch" in EntityRepository.__abstractmethods__
    assert "import_batch" in SourceRepository.__abstractmethods__
    assert "delete_batch" in SourceRepository.__abstractmethods__
    assert "patch_batch" in FaceRepository.__abstractmethods__
    assert "update_embeddings_batch" in FaceRepository.__abstractmethods__
    assert "delete_batch" in FaceRepository.__abstractmethods__
    assert "patch_batch" in TextMentionRepository.__abstractmethods__
    assert "delete_batch" in TextMentionRepository.__abstractmethods__
    assert "patch_batch" in UserRepository.__abstractmethods__
    assert "delete_batch" in UserRepository.__abstractmethods__


def test_weaviate_repositories_fully_implement_contracts() -> None:
    for repository_type in (
        WeaviateEntityRepository,
        WeaviateSourceRepository,
        WeaviateFaceRepository,
        WeaviateTextMentionRepository,
        WeaviateUserRepository,
    ):
        assert not inspect.isabstract(repository_type)


def test_postgres_repositories_fully_implement_contracts() -> None:
    for repository_type in (
        PostgresEntityRepository,
        PostgresSourceRepository,
        PostgresFaceRepository,
        PostgresTextMentionRepository,
        PostgresUserRepository,
    ):
        assert not inspect.isabstract(repository_type)
