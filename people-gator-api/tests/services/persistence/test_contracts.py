# pyright: reportPrivateUsage=false

import inspect
from unittest.mock import Mock
import uuid

import pytest

from people_gator_api.persistence.contracts import (
    Database,
    EntityRepository,
    FaceModelRepository,
    FaceRepository,
    SourceRepository,
    TextMentionRepository,
    UserRepository,
)
from people_gator_api.persistence.postgres import (
    PostgresEntityRepository,
    PostgresFaceModelRepository,
    PostgresFaceRepository,
    PostgresSourceRepository,
    PostgresTextMentionRepository,
    PostgresUserRepository,
    _cursor_fingerprint,
    _decode_cursor,
    _encode_cursor,
    postgres_database,
)
from people_gator_api.schemas.entities import EntityListFilter, EntityListRequest


def test_contract_abstract_surfaces_are_explicit() -> None:
    assert EntityRepository.__abstractmethods__ == {
        "get",
        "list",
        "create",
        "create_batch",
        "patch",
        "patch_batch",
        "delete",
        "delete_many",
        "search",
    }
    assert SourceRepository.__abstractmethods__ == {
        "lookup",
        "list",
        "get_or_create",
        "get_or_create_batch",
        "delete",
        "delete_batch",
        "search_documents",
        "search_pages",
    }
    assert FaceRepository.__abstractmethods__ == {
        "get",
        "list",
        "create",
        "create_batch",
        "patch",
        "patch_batch",
        "delete",
        "delete_batch",
        "search",
    }
    assert FaceModelRepository.__abstractmethods__ == {"register", "list"}
    assert TextMentionRepository.__abstractmethods__ == {
        "get",
        "list",
        "create",
        "create_batch",
        "patch",
        "patch_batch",
        "delete",
        "delete_batch",
    }
    assert UserRepository.__abstractmethods__ == {
        "get",
        "list",
        "get_or_create",
        "patch",
        "delete",
        "delete_batch",
    }


def test_postgres_repositories_fully_implement_contracts() -> None:
    for repository_type in (
        PostgresEntityRepository,
        PostgresFaceModelRepository,
        PostgresSourceRepository,
        PostgresFaceRepository,
        PostgresTextMentionRepository,
        PostgresUserRepository,
    ):
        assert not inspect.isabstract(repository_type)


def test_postgres_database_exposes_only_contract_repositories() -> None:
    database = postgres_database(Mock())

    assert isinstance(database, Database)
    assert isinstance(database.entities, EntityRepository)
    assert isinstance(database.sources, SourceRepository)
    assert isinstance(database.faces, FaceRepository)
    assert isinstance(database.face_models, FaceModelRepository)
    assert isinstance(database.text_mentions, TextMentionRepository)
    assert isinstance(database.users, UserRepository)


def test_postgres_cursor_is_opaque_and_bound_to_query_inputs() -> None:
    item_id = uuid.uuid4()
    query = EntityListRequest(
        filter_=EntityListFilter(entity_id=[item_id]),
        limit=20,
    )
    fingerprint = _cursor_fingerprint(query)
    cursor = _encode_cursor(item_id, fingerprint)

    assert str(item_id) not in cursor
    assert _decode_cursor(cursor, fingerprint) == item_id

    changed_query = EntityListRequest(
        filter_=EntityListFilter(entity_id=[item_id]),
        limit=10,
    )
    with pytest.raises(ValueError, match="different query"):
        _decode_cursor(cursor, _cursor_fingerprint(changed_query))


def test_postgres_cursor_rejects_malformed_values() -> None:
    query = EntityListRequest(limit=20)
    with pytest.raises(ValueError, match="malformed"):
        _decode_cursor("not-a-cursor", _cursor_fingerprint(query))
