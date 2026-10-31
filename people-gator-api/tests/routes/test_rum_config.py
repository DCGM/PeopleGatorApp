from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1.rum_config import router
from people_gator_api.settings import RumSettings, settings


def test_rum_router_works_without_app_initialization(monkeypatch):
    monkeypatch.setattr(settings, 'rum', RumSettings(enabled=True, client_token='synthetic-rum'))
    standalone = FastAPI()
    standalone.include_router(router, prefix='/api/v1')
    response = TestClient(standalone).get('/api/v1/rum-config')
    assert response.status_code == 200
    assert response.json()['clientToken'] == 'synthetic-rum'
    assert response.headers['cache-control'] == 'no-store'
    assert '/api/v1/rum-config' not in standalone.openapi()['paths']
