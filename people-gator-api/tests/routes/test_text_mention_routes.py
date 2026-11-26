import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1 import router as v1_router
from people_gator_api.schemas.mentions import (
    TextMentionPatchBatchItem,
    TextMentionResponse,
)
from people_gator_api.schemas.missing import is_missing
from people_gator_api.services.auth_service import get_auth_context
from people_gator_api.services.database_service import get_database
from people_gator_api.routes.v1.text_mentions import router


def test_text_mention_routes_are_exposed() -> None:
    app = FastAPI()
    app.include_router(router)

    paths = app.openapi()["paths"]

    assert {"get", "post"} <= paths["/text-mentions"].keys()
    assert "post" in paths["/text-mentions:batch"]
    assert {"get", "patch"} <= paths["/text-mentions/{mention_id}"].keys()


def test_text_mention_list_exposes_source_and_entity_filters() -> None:
    app = FastAPI()
    app.include_router(router)

    operation = app.openapi()["paths"]["/text-mentions"]["get"]
    parameters = {parameter["name"] for parameter in operation["parameters"]}

    assert {
        "filter.source_id",
        "filter.entity_id",
        "limit",
        "return_total_count",
        "cursor",
    } <= parameters


def test_mention_groups_expose_complete_dataset_source_modes() -> None:
    app = FastAPI()
    app.include_router(router)
    operation = app.openapi()["paths"]["/text-mention-groups"]["get"]
    parameters = {p["name"]: p for p in operation["parameters"]}
    assert parameters["group_by"]["schema"]["enum"] == ["mention", "document", "page"]
    assert {"filter.document_source_id", "filter.page_source_id", "filter.entity_id", "filter.name"} <= parameters.keys()


# --- #176: unlinked creation and text PATCH ---------------------------------

def _mention(**fields) -> TextMentionResponse:
    return TextMentionResponse.model_validate(
        {
            "mention_id": uuid.uuid4(),
            "name": "Jan Novak",
            "context": "Jan Novak signed.",
            "entity_id": None,
            "source_id": uuid.uuid4(),
            **fields,
        }
    )


def _client(**repository) -> TestClient:
    app = FastAPI()
    app.include_router(v1_router)
    app.dependency_overrides[get_database] = lambda: SimpleNamespace(
        text_mentions=SimpleNamespace(**repository)
    )
    app.dependency_overrides[get_auth_context] = lambda: SimpleNamespace(user_id=uuid.uuid4())
    return TestClient(app)


@pytest.mark.parametrize("batch", [False, True])
def test_create_accepts_a_mention_without_an_entity(batch) -> None:
    create = AsyncMock(return_value=_mention())
    create_batch = AsyncMock(return_value=[_mention()])
    body = {"name": "Jan Novak", "context": "Jan Novak signed.", "source_id": str(uuid.uuid4())}

    response = _client(create=create, create_batch=create_batch).post(
        "/api/v1/text-mentions:batch" if batch else "/api/v1/text-mentions",
        json=[body] if batch else body,
    )

    assert response.status_code == 201
    payload = (create_batch.await_args.args[0][0] if batch else create.await_args.args[0])
    assert is_missing(payload.entity_id)


@pytest.mark.parametrize("batch", [False, True])
def test_create_still_rejects_a_link_state_without_an_entity(batch) -> None:
    body = {"name": "Jan", "source_id": str(uuid.uuid4()), "entity_link_state": "manual"}

    response = _client(create=AsyncMock(), create_batch=AsyncMock()).post(
        "/api/v1/text-mentions:batch" if batch else "/api/v1/text-mentions",
        json=[body] if batch else body,
    )

    assert response.status_code == 422


def test_patch_accepts_text_and_keeps_omitted_fields() -> None:
    mention_id = uuid.uuid4()
    patch = AsyncMock(return_value=_mention(mention_id=mention_id, name="Novak"))

    response = _client(patch=patch).patch(
        f"/api/v1/text-mentions/{mention_id}", json={"name": "Novak", "context": "Later Novak."}
    )

    assert response.status_code == 200
    payload = patch.await_args.args[1]
    assert (payload.name, payload.context) == ("Novak", "Later Novak.")
    assert is_missing(payload.entity_id) and is_missing(payload.entity_link_state)
    # Only the sent fields are forwarded, so the link and its verification stay.
    assert payload.model_dump() == {"name": "Novak", "context": "Later Novak."}


def test_patch_batch_accepts_text_per_item() -> None:
    mention_id = uuid.uuid4()
    patch_batch = AsyncMock(return_value=[_mention(mention_id=mention_id)])

    response = _client(patch_batch=patch_batch).patch(
        "/api/v1/text-mentions:batch",
        json=[{"mention_id": str(mention_id), "context": None}],
    )

    assert response.status_code == 200
    (item,) = patch_batch.await_args.args[0]
    assert isinstance(item, TextMentionPatchBatchItem)
    assert item.context is None and is_missing(item.name)


@pytest.mark.parametrize("name", ["", "   ", None])
@pytest.mark.parametrize("batch", [False, True])
def test_patch_rejects_an_empty_name(name, batch) -> None:
    mention_id = uuid.uuid4()
    client = _client(patch=AsyncMock(), patch_batch=AsyncMock())
    response = (
        client.patch("/api/v1/text-mentions:batch", json=[{"mention_id": str(mention_id), "name": name}])
        if batch
        else client.patch(f"/api/v1/text-mentions/{mention_id}", json={"name": name})
    )

    assert response.status_code == 422
