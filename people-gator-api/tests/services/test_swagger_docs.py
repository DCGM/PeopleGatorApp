"""Docs consume the existing browser session without issuer routes in the API."""
from fastapi.testclient import TestClient
from people_gator_api.app import get_app


def test_swagger_loads_frontend_session_bridge_and_keeps_canonical_security():
    app = get_app()
    response = TestClient(app).get("/docs")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert 'src="/swagger-auth.js"' in response.text
    assert "window.ui = SwaggerUIBundle" in response.text
    assert "requestInterceptor:" in response.text
    assert "peoplegator:docs-ready" in response.text
    schema = app.openapi()
    security = schema["components"]["securitySchemes"]
    assert security["PeopleGatorBearer"]["type"] == "http"
    assert "/login.html?return=%2Fdocs" in security["PeopleGatorBearer"]["description"]
    assert security["PeopleGatorAPIKey"]["type"] == "apiKey"
    assert not any(path.startswith(("/token/", "/.well-known/")) for path in schema["paths"])
    assert "/docs" not in schema["paths"]


def test_swagger_preserves_proxy_root_path_for_openapi():
    response = TestClient(get_app(), root_path="/proxy").get("/docs")
    assert response.status_code == 200
    assert "url: '/proxy/openapi.json'" in response.text
    assert 'src="/swagger-auth.js"' in response.text
