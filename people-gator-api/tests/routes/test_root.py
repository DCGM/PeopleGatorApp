from fastapi import FastAPI
from fastapi.testclient import TestClient

from people_gator_api.routes.v1.root import router


def test_health_returns_ok() -> None:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}