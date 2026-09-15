from typing import cast

from fastapi import FastAPI
from fastapi.routing import APIRoute

from people_gator_api.routes.v1.annotations import router as annotations_router
from people_gator_api.routes.v1.entities import router as entities_router
from people_gator_api.routes.v1.media import router as media_router
from people_gator_api.routes.v1.sources import router as sources_router


def test_media_router_exposes_pages_and_images_without_relationship_routes() -> None:
    paths = {cast(APIRoute, route).path_format for route in media_router.routes}

    assert "/pages" in paths
    assert "/pages/{page_source_id}" in paths
    assert "/pages/{library}/{document_id}/{page_id}" in paths
    assert "/pages/{library}/{page_id}" in paths
    assert "/documents/{library}/{document_id}" in paths
    assert "/documents" in paths
    assert "/documents/{document_source_id}" in paths
    assert "/pages/by-url" in paths
    assert "/documents/by-url" in paths
    assert "/images/by-url" in paths
    assert "/images" in paths
    assert "/images/{image_id}" in paths
    assert not any("/scans" in path for path in paths)
    assert not any(
        path.endswith(("/mentions", "/entities", "/detections")) for path in paths
    )

    source_paths = {
        cast(APIRoute, route).path_format for route in sources_router.routes
    }
    assert "/sources/by-url" in source_paths


def test_annotation_lists_expose_shared_typed_source_filters() -> None:
    app = FastAPI()
    app.include_router(annotations_router)
    app.include_router(entities_router)
    spec = app.openapi()

    for path in ("/faces", "/entities", "/page-mentions", "/document-mentions"):
        parameters = {
            parameter["name"] for parameter in spec["paths"][path]["get"]["parameters"]
        }
        assert {"source_id", "page", "document", "image"} <= parameters


def test_documents_expose_full_immutable_rest_interface() -> None:
    app = FastAPI()
    app.include_router(media_router)
    document_paths = app.openapi()["paths"]

    assert {"get", "post"} <= set(document_paths["/documents"])
    assert {"get", "delete"} <= set(document_paths["/documents/{document_source_id}"])
    assert "get" in document_paths["/documents/{library}/{document_id}"]
    assert "get" in document_paths["/documents/by-url"]
