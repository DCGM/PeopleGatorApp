"""People count bounds use the same strict transport-neutral integer contract."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from people_gator_api.routes.v1.query_dependencies import EntityListFilterDependency
from people_gator_api.schemas.entities import EntityListFilter, EntityListRequest
from people_gator_api.schemas.search import SearchEntitiesRequest

app = FastAPI()
@app.get('/entities')
def entities(filters: EntityListFilterDependency):
    return filters.model_dump(exclude_unset=True)
client = TestClient(app)

@pytest.mark.parametrize('kind', ['faces', 'mentions'])
@pytest.mark.parametrize('bound', ['min', 'max'])
def test_bounds(kind, bound):
    name = f'{bound}_{kind}_total_count'
    assert name not in client.get('/entities').json()
    for value in (0, 1, 9_007_199_254_740_991):
        assert getattr(EntityListFilter(**{name: value}), name) == value
        response = client.get('/entities', params={'filter.' + name: str(value)})
        assert response.status_code == 200
        assert response.json()[name] == value
    for value in ('-1', '1.5', '1.0', '-0', '1e2', 'true', '', 'nan', ' 2 ', '9007199254740992'):
        assert client.get('/entities', params={'filter.' + name: value}).status_code == 422
    for value in (-1, 1.5, 1.0, True, False, None, 9_007_199_254_740_992):
        with pytest.raises(ValidationError):
            EntityListFilter(**{name: value})
    assert client.get('/entities', params={f'filter.min_{kind}_total_count': 2, f'filter.max_{kind}_total_count': 1}).status_code == 422
    assert client.get('/entities', params={f'filter.min_{kind}_total_count': 0, f'filter.max_{kind}_total_count': 0}).status_code == 200

@pytest.mark.parametrize('field', ['faces_total_count', 'mentions_total_count', 'annotations_total_count'])
def test_sort_defaults(field):
    assert EntityListRequest(limit=12, sort=field).effective_sort() == (field, 'desc')
    assert SearchEntitiesRequest(limit=12, query={'text': ['Ada']}, sort=field).effective_sort() == (field, 'desc')


def test_weaviate_rejects_count_filters_instead_of_ignoring_them():
    from people_gator_api.persistence.weaviate import _require_default_sort
    with pytest.raises(NotImplementedError, match="PostgreSQL"):
        _require_default_sort(EntityListRequest(limit=12, filter_=EntityListFilter(max_faces_total_count=0)))
