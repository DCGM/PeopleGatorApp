from fastapi import FastAPI

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
