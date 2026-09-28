from fastapi import FastAPI

from people_gator_api.routes.v1.entities import router


def test_entity_merge_route_has_explicit_request_and_result() -> None:
    app = FastAPI()
    app.include_router(router)

    spec = app.openapi()
    operation = spec["paths"]["/entities/{target_entity_id}:merge"]["post"]
    assert operation["requestBody"]["required"] is True
    request_schema = spec["components"]["schemas"]["EntityMergeFromRequest"]
    assert request_schema["required"] == ["source_entity_id"]
    assert {"description", "short_description"} <= request_schema["properties"].keys()
    assert "200" in operation["responses"]
    assert "omission preserves" in operation["description"]

    batch_operation = spec["paths"]["/entities/{target_entity_id}:merge-batch"]["post"]
    batch_schema = spec["components"]["schemas"]["EntityMergeBatchRequest"]
    assert batch_schema["required"] == ["source_entity_ids"]
    assert {"description", "short_description"} <= batch_schema["properties"].keys()
    assert batch_schema["properties"]["source_entity_ids"]["minItems"] == 1
    assert "200" in batch_operation["responses"]
