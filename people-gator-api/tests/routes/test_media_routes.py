from typing import cast

from fastapi import FastAPI
from fastapi.routing import APIRoute

from people_gator_api.routes.v1.annotations import router as annotations_router
from people_gator_api.routes.v1.entities import router as entities_router
from people_gator_api.routes.v1.media import router as media_router
from people_gator_api.routes.v1.sources import router as sources_router


def test_media_router_exposes_typed_source_and_page_subresource_routes() -> None:
    paths = {cast(APIRoute, route).path_format for route in media_router.routes}

    assert "/pages" in paths
    assert "/pages/{page_source_id}" in paths
    assert "/pages/lookup" in paths
    assert "/pages/{page_source_id}/page-layout" in paths
    assert "/pages/{page_source_id}/text-mentions-spans" in paths
    assert "/documents" in paths
    assert "/documents/{document_source_id}" in paths
    assert "/documents/lookup" in paths
    assert "/images/lookup" in paths
    assert "/images" in paths
    assert "/images/{image_id}" in paths
    assert not any("/scans" in path for path in paths)
    assert not any(
        path.endswith(("/mentions", "/entities", "/detections")) for path in paths
    )

    source_paths = {
        cast(APIRoute, route).path_format for route in sources_router.routes
    }
    assert "/sources/lookup" in source_paths


def test_source_list_only_accepts_url_as_its_filter() -> None:
    app = FastAPI()
    app.include_router(sources_router)

    parameters = app.openapi()["paths"]["/sources"]["get"]["parameters"]
    assert {parameter["name"] for parameter in parameters} == {
        "url",
        "limit",
        "after_id",
    }


def test_annotation_lists_only_accept_direct_source_filters() -> None:
    app = FastAPI()
    app.include_router(annotations_router)
    app.include_router(entities_router)
    spec = app.openapi()

    face_parameters = {
        parameter["name"]
        for parameter in spec["paths"]["/faces"]["get"]["parameters"]
    }
    source_selectors = {"source_id", "page", "document", "image"}
    assert face_parameters & source_selectors == {"source_id"}
    assert "entity_id" in face_parameters

    entity_parameters = {
        parameter["name"]
        for parameter in spec["paths"]["/entities"]["get"]["parameters"]
    }
    assert entity_parameters & source_selectors == {"source_id"}

    assert "/page-mentions" not in spec["paths"]
    assert "/document-mentions" not in spec["paths"]
    assert "/entities/{entity_id}/mentioned-in/{source_id}" not in spec["paths"]


def test_documents_expose_full_immutable_rest_interface() -> None:
    app = FastAPI()
    app.include_router(media_router)
    document_paths = app.openapi()["paths"]

    assert {"get", "post"} <= set(document_paths["/documents"])
    assert {"get", "delete"} <= set(document_paths["/documents/{document_source_id}"])
    assert "get" in document_paths["/documents/lookup"]

    lookup_parameters = {
        parameter["name"]: parameter["required"]
        for parameter in document_paths["/documents/lookup"]["get"]["parameters"]
    }
    assert lookup_parameters == {"library": True, "document_id": True}


def test_typed_lookups_only_resolve_resources() -> None:
    app = FastAPI()
    app.include_router(media_router)
    paths = app.openapi()["paths"]

    expected_parameters = {
        "/documents/lookup": {"library", "document_id"},
        "/pages/lookup": {"library", "document_id", "page_id"},
        "/images/lookup": {"url"},
    }
    for path, expected in expected_parameters.items():
        parameters = paths[path]["get"]["parameters"]
        assert {parameter["name"] for parameter in parameters} == expected
        assert all(parameter["required"] for parameter in parameters)

    assert not {
        "/pages/lookup/image",
        "/pages/lookup/page-layout",
        "/pages/lookup/text-mentions-spans",
        "/images/lookup/content",
    } & paths.keys()
