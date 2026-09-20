from fastapi.testclient import TestClient

from people_gator_api.app import get_app


def test_localhost_origin_is_allowed() -> None:
    client = TestClient(get_app())

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
    assert "authorization" in response.headers["access-control-allow-headers"]


def test_non_local_origin_is_not_allowed() -> None:
    client = TestClient(get_app())

    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "https://example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers