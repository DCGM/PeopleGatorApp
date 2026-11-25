"""Public browser-app configuration, independent of app initialization."""
from fastapi import APIRouter, Response

from people_gator_api.settings import settings

router = APIRouter(include_in_schema=False)


@router.get("/app-config")
async def app_config(response: Response):
    # Deliberately public: never serialize Settings here. The public login is an
    # account meant for everyone, so its password is not a secret.
    response.headers["Cache-Control"] = "no-store"
    login = settings.public_login
    return {
        "publicLogin": {"username": login.username, "password": login.password} if login else None,
    }
