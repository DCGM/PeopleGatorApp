"""The same strict count contract on HTTP and typed list/search requests."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from people_gator_api.schemas.annotation_counts import ANNOTATION_COUNT_FIELDS
from people_gator_api.schemas.sources import DocumentListFilter, PageListFilter
from people_gator_api.schemas.search import SearchDocumentsRequest, SearchPagesRequest
from people_gator_api.routes.v1.query_dependencies import (
    DocumentListFilterDependency,
    PageListFilterDependency,
)


@pytest.fixture(scope="module")
def client():
    app = FastAPI()

    @app.get("/documents")
    def documents(filters: DocumentListFilterDependency):
        return filters.model_dump(exclude_unset=True)

    @app.get("/pages")
    def pages(filters: PageListFilterDependency):
        return filters.model_dump(exclude_unset=True)

    return TestClient(app)


@pytest.mark.parametrize("field", ANNOTATION_COUNT_FIELDS)
@pytest.mark.parametrize(
    "model,path", [(DocumentListFilter, "/documents"), (PageListFilter, "/pages")]
)
def test_minimum_contract(client, model, path, field):
    name = "min_" + field
    for value in (0, 1, 10, 9_007_199_254_740_991):
        assert getattr(model(**{name: value}).to_generic(), name) == value
        response = client.get(path, params={"filter." + name: str(value)})
        assert response.status_code == 200, response.text
        assert response.json()[name] == value
    assert name not in client.get(path).json()
    for value in ("-1", "1.5", "1.0", "-0", "1e2", "true", "", "nan", " 2 "):
        assert client.get(path, params={"filter." + name: value}).status_code == 422
    for value in (-1, 1.5, 1.0, True, False, None, "bad"):
        with pytest.raises(ValidationError):
            model(**{name: value})


@pytest.mark.parametrize("request_type", [SearchDocumentsRequest, SearchPagesRequest])
@pytest.mark.parametrize("field", ANNOTATION_COUNT_FIELDS)
def test_search_request_count_contract_and_default_direction(request_type, field):
    result = request_type.model_validate(
        {
            "limit": 12,
            "query": {"text": ["ledger"]},
            "filter_": {"min_" + field: 2},
            "sort": field,
        }
    )
    assert result.effective_sort() == (field, "desc")
    with pytest.raises(ValidationError):
        request_type.model_validate(
            {
                "limit": 12,
                "query": {"text": ["ledger"]},
                "filter_": {"min_" + field: 1.5},
            }
        )
