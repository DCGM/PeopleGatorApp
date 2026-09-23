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
        "source_id",
        "entity_id",
        "limit",
        "return_total_count",
        "cursor",
    } <= parameters
