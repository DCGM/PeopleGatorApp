import uuid
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.schemas.annotation_counts import ANNOTATION_COUNT_FIELDS
from people_gator_api.routes.v1 import router
from people_gator_api.routes.v1.query_dependencies import (
    FaceListFilterDependency,
    PageListFilterDependency,
    SearchListRequestDependency,
    SearchQueryDependency,
)


PAGINATION_PARAMETERS = {"limit", "return_total_count", "cursor"}
SORT_PARAMETERS = {"sort", "sort_direction"}
SORTABLE_LISTS = {"/entities", "/faces", "/text-mentions", "/documents", "/pages"}
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
    "/faces": {"entity_id", "source_id", "detection_id", "is_assigned"},
    "/text-mentions": {"entity_id", "source_id", "name"},
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
LIST_FILTERS["/documents"].add("has_unassigned_faces")
for path in ("/documents", "/pages"):
    LIST_FILTERS[path].update("min_" + field for field in ANNOTATION_COUNT_FIELDS)

# Every source, annotation and entity list shares one canonical scope and
# latest-modification vocabulary (#52).
SHARED_FILTERS = {
    "library", "document_source_id", "page_source_id", "last_touched_from",
    "last_touched_to", "last_touched_by_user_id", "last_touched_by_api_key_id",
}
for path, fields in LIST_FILTERS.items():
    if path != "/users":
        fields.update(SHARED_FILTERS)

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
        *(SORT_PARAMETERS if path in SORTABLE_LISTS else set()),
    }


@pytest.mark.parametrize(("path", "fields"), SEARCH_FILTERS.items())
def test_search_endpoints_expose_query_filter_and_pagination_groups(
    openapi: dict[str, Any],
    path: str,
    fields: set[str],
) -> None:
    assert _parameter_names(openapi, path) == {
        *QUERY_PARAMETERS,
        *({"query.entity_id", "query.entity_annotations"} if path in {"/search-entities", "/search-faces"} else set()),
        *(f"filter.{field}" for field in fields),
        *({"filter.entity_link_state"} if path != "/users" else set()),
        *PAGINATION_PARAMETERS,
        *SORT_PARAMETERS,
    }


def _sort_values(openapi: dict[str, Any], path: str) -> list[str]:
    paths = cast(dict[str, Any], openapi["paths"])
    parameters = cast(list[dict[str, Any]], paths[f"/api/v1{path}"]["get"]["parameters"])
    schema = next(item for item in parameters if item["name"] == "sort")["schema"]
    reference = next(option["$ref"] for option in schema["anyOf"] if "$ref" in option)
    component = openapi["components"]["schemas"][reference.rsplit("/", 1)[-1]]
    return cast(list[str], component["enum"])


@pytest.mark.parametrize(("path", "values"), [
    ("/entities", ["name", "entity_id", "last_touched_at", "created_at"]),
    ("/search-entities", ["relevance", "name", "entity_id", "last_touched_at", "created_at"]),
    ("/documents", ["name", "document_id", "library", "page_count", "last_touched_at"]),
    ("/search-documents", ["relevance", "name", "document_id", "library", "page_count", "last_touched_at"]),
    ("/pages", ["page_number", "library", "document_id", "page_id", "last_touched_at"]),
    ("/search-pages", ["page_number", "relevance", "library", "document_id", "page_id", "last_touched_at"]),
    ("/faces", ["detection_id", "last_touched_at", "link_state", "confidence", "source"]),
    ("/search-faces", ["relevance", "detection_id", "last_touched_at", "link_state", "confidence", "source"]),
    ("/text-mentions", ["text", "mention_id", "last_touched_at", "link_state", "source"]),
    ("/text-mention-groups", ["text", "count", "last_touched_at"]),
])
def test_sort_fields_are_resource_allowlists(openapi: dict[str, Any], path: str, values: list[str]) -> None:
    """Relevance is offered only where a search score exists."""
    if path in {"/documents", "/search-documents", "/pages", "/search-pages"}:
        values = [*ANNOTATION_COUNT_FIELDS, *values]
    assert _sort_values(openapi, path) == values


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


@pytest.mark.parametrize('path', ['/sources', '/documents', '/pages', '/images', '/search-documents', '/search-pages'])
@pytest.mark.parametrize('parameters', [
    {'filter.last_touched_from': '2026-01-01T00:00:00'},
    {'filter.last_touched_from': 'not-a-date'},
    {'filter.last_touched_from': '2026-02-01T00:00:00Z', 'filter.last_touched_to': '2026-01-01T00:00:00Z'},
    {'filter.last_touched_by_user_id': 'not-a-uuid'},
    {'filter.last_touched_by_api_key_id': 'not-a-uuid'},
    {'filter.entity_link_state': 'unassigned'},
])
def test_source_processing_query_validation_before_repository_access(path, parameters):
    from people_gator_api.routes.v1.query_dependencies import source_list_filter_dependency, document_list_filter_dependency, image_list_filter_dependency, page_list_filter_dependency
    from fastapi import Depends
    dependencies = {'/sources': source_list_filter_dependency, '/documents': document_list_filter_dependency, '/images': image_list_filter_dependency}
    dependency = dependencies.get(path, document_list_filter_dependency if path == '/search-documents' else page_list_filter_dependency)
    app = FastAPI()
    @app.get(path)
    def endpoint(filter=Depends(dependency)):
        return {'valid': True}
    assert TestClient(app).get(path, params=parameters).status_code == 422


def test_sort_parameters_reject_fields_outside_the_allowlist() -> None:
    from people_gator_api.routes.v1.query_dependencies import (
        EntityListSortDependency,
        EntitySearchSortDependency,
    )

    app = FastAPI()

    async def _list(sort: EntityListSortDependency) -> dict[str, object]:
        return {"sort": sort.sort, "direction": sort.sort_direction}

    async def _search(sort: EntitySearchSortDependency) -> dict[str, object]:
        return {"sort": sort.sort, "direction": sort.sort_direction}

    app.get("/list")(_list)
    app.get("/search")(_search)
    client = TestClient(app)
    assert client.get("/list", params={"sort": "name", "sort_direction": "desc"}).json() == {
        "sort": "name", "direction": "desc"}
    assert client.get("/list").json() == {"sort": None, "direction": None}
    assert client.get("/list", params={"sort": "relevance"}).status_code == 422
    assert client.get("/list", params={"sort": "pg_demo_entities.id"}).status_code == 422
    assert client.get("/list", params={"sort": "name", "sort_direction": "up"}).status_code == 422
    assert client.get("/search", params={"sort": "relevance"}).json()["sort"] == "relevance"
