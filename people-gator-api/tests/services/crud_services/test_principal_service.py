from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.principals import ModelAgentCreateRequest
from people_gator_api.services.crud_services import principal_service


def _model_agent_payload() -> ModelAgentCreateRequest:
    return ModelAgentCreateRequest(
        display_name="Face recognizer",
        is_active=True,
        model_slug="face-recognizer",
        model_version="1.0",
    )


@pytest.mark.asyncio
async def test_create_model_agent_rejects_duplicate_without_writing() -> None:
    existing_id = uuid.uuid4()
    insert_called = False

    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[SimpleNamespace(uuid=existing_id)])

    class _Data:
        async def insert(self, **_kwargs: object) -> None:
            nonlocal insert_called
            insert_called = True

    collection = SimpleNamespace(query=_Query(), data=_Data())

    def get_collection(_name: str) -> SimpleNamespace:
        return collection

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))

    with pytest.raises(principal_service.PrincipalAlreadyExistsError):
        await principal_service.create_model_agent(
            client,  # pyright: ignore[reportArgumentType] - lightweight Weaviate client double.
            _model_agent_payload(),
            uuid.uuid4(),
        )

    assert insert_called is False


@pytest.mark.asyncio
async def test_create_model_agent_inserts_new_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    principal_id = uuid.uuid4()
    inserted: dict[str, object] = {}

    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> SimpleNamespace:
            return SimpleNamespace(objects=[])

        async def fetch_object_by_id(
            self,
            object_id: uuid.UUID,
            **_kwargs: object,
        ) -> SimpleNamespace:
            del object_id
            raise AssertionError("create must not re-read the inserted principal")

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

    client = SimpleNamespace(collections=SimpleNamespace(get=get_collection))
    monkeypatch.setattr(principal_service, "new_uuid6", lambda: principal_id)

    created = await principal_service.create_model_agent(
        client,  # pyright: ignore[reportArgumentType] - lightweight Weaviate client double.
        _model_agent_payload(),
        uuid.uuid4(),
    )

    assert inserted["uuid"] == principal_id
    assert created.principal_id == principal_id
    assert created.model_slug == "face-recognizer"
    assert created.model_version == "1.0"
