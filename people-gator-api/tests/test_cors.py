from fastapi.testclient import TestClient
import pytest

from people_gator_api.app import get_app
from people_gator_api.settings import CorsSettings, settings


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


@pytest.mark.parametrize("origin, allowed", [
    ("http://dev.example.com:18080", True),
    ("http://devXexample.com:18080", False),
    ("http://dev.example.com:8080", False),
    ("https://dev.example.com:18080", False),
    ("http://localhost:18080", False),
])
def test_configured_origin_is_matched_exactly(
    monkeypatch: pytest.MonkeyPatch, origin: str, allowed: bool,
) -> None:
    monkeypatch.setattr(settings, "cors", CorsSettings(
        allow_origins=["http://dev.example.com:18080"],
        allow_origin_regex="",
    ))
    response = TestClient(get_app()).options(
        "/api/v1/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == (200 if allowed else 400)
    if allowed:
        assert response.headers["access-control-allow-origin"] == origin
    else:
        assert "access-control-allow-origin" not in response.headers
