from fastapi import FastAPI

from people_gator_api.routes.v1.face_models import router


def test_face_model_routes_are_admin_only() -> None:
    app = FastAPI()
    app.include_router(router)
    operations = app.openapi()["paths"]["/face-models"]

    assert {"get", "post"} <= operations.keys()
    for method in ("get", "post"):
        security = operations[method]["security"]
        assert any(
            "people-gator:admin" in scopes
            for item in security
            for scopes in item.values()
        )


def test_face_model_registration_requires_stub_and_dimension() -> None:
    app = FastAPI()
    app.include_router(router)
    schema = app.openapi()["components"]["schemas"]["FaceModelRegisterRequest"]

    assert set(schema["required"]) == {"model_stub", "embedding_dim"}
