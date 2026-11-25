from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1.app_config import router
from people_gator_api.settings import PublicLoginSettings, Settings, settings


def client() -> TestClient:
    standalone = FastAPI()
    standalone.include_router(router, prefix='/api/v1')
    return TestClient(standalone)


def test_app_config_publishes_the_public_login(monkeypatch):
    monkeypatch.setattr(settings, 'public_login', PublicLoginSettings(username='guest', password='open'))
    response = client().get('/api/v1/app-config')
    assert response.status_code == 200
    assert response.json() == {'publicLogin': {'username': 'guest', 'password': 'open'}}
    assert response.headers['cache-control'] == 'no-store'
    assert '/api/v1/app-config' not in client().app.openapi()['paths']


def test_app_config_has_no_public_login_by_default(monkeypatch):
    monkeypatch.setattr(settings, 'public_login', None)
    assert client().get('/api/v1/app-config').json() == {'publicLogin': None}


def test_public_login_is_one_setting_with_both_credentials(monkeypatch):
    monkeypatch.setenv('PEOPLE_GATOR_API__PUBLIC_LOGIN__USERNAME', 'guest')
    monkeypatch.setenv('PEOPLE_GATOR_API__PUBLIC_LOGIN__PASSWORD', 'open')
    assert Settings().public_login == PublicLoginSettings(username='guest', password='open')
    monkeypatch.delenv('PEOPLE_GATOR_API__PUBLIC_LOGIN__USERNAME')
    monkeypatch.delenv('PEOPLE_GATOR_API__PUBLIC_LOGIN__PASSWORD')
    monkeypatch.setenv('PEOPLE_GATOR_API__PUBLIC_LOGIN', '{"username": "guest", "password": "open"}')
    assert Settings().public_login == PublicLoginSettings(username='guest', password='open')
