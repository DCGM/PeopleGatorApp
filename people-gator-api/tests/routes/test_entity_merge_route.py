from fastapi import FastAPI

from people_gator_api.routes.v1.entities import router


def test_entity_merge_route_has_explicit_request_and_result() -> None:
    app = FastAPI()
    app.include_router(router)

    spec = app.openapi()
    operation = spec["paths"]["/entities/{target_entity_id}:merge"]["post"]
    assert operation["requestBody"]["required"] is True
    request_schema = spec["components"]["schemas"]["EntityMergeFromRequest"]
    assert request_schema["required"] == ["version", "sources"]
    assert {"description", "short_description"} <= request_schema["properties"].keys()
    assert "200" in operation["responses"]
    assert "omission preserves" in operation["description"]

    batch_operation = spec["paths"]["/entities/{target_entity_id}:merge-batch"]["post"]
    batch_schema = spec["components"]["schemas"]["EntityMergeBatchRequest"]
    assert batch_schema["required"] == ["version", "sources"]
    assert {"description", "short_description"} <= batch_schema["properties"].keys()
    assert batch_schema["properties"]["sources"]["minItems"] == 1
    assert "200" in batch_operation["responses"]


def test_single_and_batch_merge_require_admin_scope() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    for suffix in ("merge", "merge-batch"):
        operation = paths[f"/entities/{{target_entity_id}}:{suffix}"]["post"]
        assert any(
            "people-gator:admin" in scopes
            for item in operation["security"]
            for scopes in item.values()
        )
