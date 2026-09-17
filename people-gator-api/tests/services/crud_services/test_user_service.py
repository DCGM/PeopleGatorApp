from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.services.crud_services import user_service


@pytest.mark.asyncio
async def test_get_or_create_user_returns_existing_user_without_writing() -> None:
    user_id = uuid.uuid4()
    insert_called = False
    existing_user = SimpleNamespace(
        uuid=user_id,
        properties={
            "display_name": "Existing user",
            "is_active": True,
            "external_subject": "subject",
            "external_issuer": "issuer",
            "email": "user@example.test",
        },
        references={},
    )

    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[existing_user])

    class _Data:
        async def insert(self, **_kwargs: object) -> None:
            nonlocal insert_called
            insert_called = True

    collection = SimpleNamespace(query=_Query(), data=_Data())
    def get_collection(_name: str) -> SimpleNamespace:
        return collection

    client = SimpleNamespace(
        collections=SimpleNamespace(get=get_collection)
    )

    found = await user_service.get_or_create_user(
        client,  # pyright: ignore[reportArgumentType]
        external_subject="subject",
        external_issuer="issuer",
    )

    assert found.user_id == user_id
    assert found.email == "user@example.test"
    assert insert_called is False


@pytest.mark.asyncio
async def test_get_or_create_user_inserts_new_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    inserted: dict[str, object] = {}

    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[])

    class _Data:
        async def insert(
            self,
            *,
            uuid: uuid.UUID,
            properties: dict[str, object],
        ) -> None:
            inserted["uuid"] = uuid
            inserted["properties"] = properties

    collection = SimpleNamespace(query=_Query(), data=_Data())
    def get_collection(_name: str) -> SimpleNamespace:
        return collection

    client = SimpleNamespace(
        collections=SimpleNamespace(get=get_collection)
    )
    monkeypatch.setattr(user_service, "new_uuid6", lambda: user_id)

    created = await user_service.get_or_create_user(
        client,  # pyright: ignore[reportArgumentType]
        external_subject="subject",
        external_issuer="issuer",
    )

    assert inserted["uuid"] == user_id
    assert inserted["properties"] == {
        "display_name": "subject",
        "is_active": True,
        "external_subject": "subject",
        "external_issuer": "issuer",
        "email": None,
    }
    assert created.user_id == user_id
