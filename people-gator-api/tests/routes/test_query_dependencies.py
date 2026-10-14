import uuid
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1 import router
from people_gator_api.routes.v1.query_dependencies import (
    FaceListFilterDependency,
    PageListFilterDependency,
    SearchListRequestDependency,
    SearchQueryDependency,
)


PAGINATION_PARAMETERS = {"limit", "return_total_count", "cursor"}
QUERY_PARAMETERS = {
    "query.text",
    "query.face_id",
    "query.face_embedding_model",
    "query.exclude_reference_face_id",
    "query.score_aggregation",
    "query.score_fusion",
}
LIST_FILTERS = {
    "/entities": {
        "entity_id",
        "entity_type",
        "wikidata_id",
        "nlcr_authority_id",
        "source_id",
        "detection_id",
        "mention_id",
        "has_mentions",
        "has_detections",
        "last_touched_from", "last_touched_to", "document_source_id",
        "last_touched_by_user_id", "last_touched_by_api_key_id",
    },
    "/faces": {"entity_id", "source_id", "detection_id"},
    "/text-mentions": {"entity_id", "source_id"},
    "/users": {
        "display_name",
        "is_active",
        "external_subject",
        "external_issuer",
        "email",
    },
    "/sources": {
        "source_type",
        "url",
        "source_id",
        "entity_id",
        "detection_id",
        "mention_id",
    },
    "/documents": {
        "url",
        "library",
        "document_id",
        "source_id",
        "entity_id",
        "detection_id",
        "mention_id",
    },
    "/pages": {
        "url",
        "library",
        "document_id",
        "page_id",
        "source_id",
        "entity_id",
        "detection_id",
        "mention_id",
        "has_mentions",
        "has_faces",
        "has_entities",
    },
    "/images": {
        "url",
        "source_id",
        "entity_id",
        "detection_id",
        "mention_id",
    },
}
for path in ("/sources", "/documents", "/pages", "/images"):
    LIST_FILTERS[path].update({"last_touched_from", "last_touched_to", "last_touched_by_user_id", "last_touched_by_api_key_id"})
LIST_FILTERS["/documents"].add("has_unassigned_faces")

SEARCH_FILTERS = {
    "/search-entities": LIST_FILTERS["/entities"],
    "/search-faces": LIST_FILTERS["/faces"],
    "/search-pages": LIST_FILTERS["/pages"],
    "/search-documents": LIST_FILTERS["/documents"],
}


@pytest.fixture(scope="module")
def openapi() -> dict[str, Any]:
    app = FastAPI()
    app.include_router(router)
    return app.openapi()


def _parameter_names(openapi: dict[str, Any], path: str) -> set[str]:
    paths = cast(dict[str, Any], openapi["paths"])
    operation = cast(dict[str, Any], paths[f"/api/v1{path}"]["get"])
    parameters = cast(list[dict[str, Any]], operation["parameters"])
    return {cast(str, parameter["name"]) for parameter in parameters}


@pytest.mark.parametrize(("path", "fields"), LIST_FILTERS.items())
def test_list_endpoints_expose_namespaced_filters(
    openapi: dict[str, Any],
    path: str,
    fields: set[str],
) -> None:
    assert _parameter_names(openapi, path) == {
        *(f"filter.{field}" for field in fields),
        *({"filter.entity_link_state"} if path != "/users" else set()),
        *PAGINATION_PARAMETERS,
    }


@pytest.mark.parametrize(("path", "fields"), SEARCH_FILTERS.items())
def test_search_endpoints_expose_query_filter_and_pagination_groups(
    openapi: dict[str, Any],
    path: str,
    fields: set[str],
) -> None:
    assert _parameter_names(openapi, path) == {
        *QUERY_PARAMETERS,
        *(f"filter.{field}" for field in fields),
        *({"filter.entity_link_state"} if path != "/users" else set()),
        *PAGINATION_PARAMETERS,
    }


def test_dependencies_parse_dotted_parameters_into_typed_models() -> None:
    app = FastAPI()

    async def _probe(
        query: SearchQueryDependency,
        filter: FaceListFilterDependency,
        list_request: SearchListRequestDependency,
    ) -> dict[str, object]:
        return {
            "query": query.model_dump(mode="json"),
            "filter": filter.model_dump(mode="json"),
            "list_request": list_request.model_dump(mode="json"),
        }

    app.get("/probe")(_probe)

    face_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    response = TestClient(app).get(
        "/probe",
        params=[
            ("query.text", "Ada"),
            ("query.text", "Lovelace"),
            ("query.face_id", str(face_id)),
            ("filter.entity_id", str(entity_id)),
            ("limit", "7"),
            ("return_total_count", "true"),
            ("cursor", "opaque"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["text"] == ["Ada", "Lovelace"]
    assert payload["query"]["face_id"] == [str(face_id)]
    assert payload["filter"] == {"entity_id": [str(entity_id)]}
    assert payload["list_request"] == {
        "limit": 7,
        "return_total_count": True,
        "cursor": "opaque",
    }


def test_page_dependency_preserves_false_presence_filters() -> None:
    app = FastAPI()

    async def _probe(filter: PageListFilterDependency) -> dict[str, object]:
        return filter.model_dump(mode="json")

    app.get("/probe")(_probe)
    response = TestClient(app).get(
        "/probe",
        params={
            "filter.has_mentions": "true",
            "filter.has_faces": "false",
            "filter.has_entities": "false",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "has_mentions": True,
        "has_faces": False,
        "has_entities": False,
    }


def test_search_query_dependency_keeps_cross_field_validation() -> None:
    app = FastAPI()

    async def _probe(query: SearchQueryDependency) -> dict[str, object]:
        return query.model_dump(mode="json")

    app.get("/probe")(_probe)

    response = TestClient(app).get("/probe")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "invalid_search"
