"""Translation endpoint backed by the OpenRouter API."""

from fastapi import APIRouter, status

from people_gator_api.schemas.translation import (
    TranslationRequest,
    TranslationResponse,
)
from people_gator_api.services.auth_service import BrowseActorDependency
from people_gator_api.utils.http_errors import raise_api_error
from people_gator_api.services.openrouter_service import (
    OpenRouterError,
    get_openrouter_service,
)
from people_gator_api.services.translation_service import (
    TranslationLanguageError,
    translate_text,
)
from people_gator_api.settings import settings

router = APIRouter(tags=["translation"])


@router.post(
    "/translate",
    response_model=TranslationResponse,
    status_code=status.HTTP_200_OK,
)
async def translate_route(
    payload: TranslationRequest,
    user: BrowseActorDependency,
) -> TranslationResponse:
    del user
    openrouter = settings.openrouter
    if not openrouter:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY, "translation_failed", "OpenRouter settings are not configured"
        )
    try:
        return await translate_text(
            payload, openrouter, get_openrouter_service()
        )
    except TranslationLanguageError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    except OpenRouterError as exc:
        raise_api_error(
            status.HTTP_502_BAD_GATEWAY, "translation_failed", str(exc)
        )
