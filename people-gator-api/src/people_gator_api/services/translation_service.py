from people_gator_api.schemas.translation import TranslationRequest, TranslationResponse
from people_gator_api.services.openrouter_service import HttpOpenRouterService
from people_gator_api.settings import OpenRouterSettings


class TranslationLanguageError(ValueError):
    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


async def translate_text(
    payload: TranslationRequest,
    openrouter_cfg: OpenRouterSettings,
    openrouter_service: HttpOpenRouterService,
) -> TranslationResponse:
    if payload.language not in openrouter_cfg.allowed_languages:
        raise TranslationLanguageError(
            f"Language '{payload.language.value}' is not in the allowed language list.",
            status_code=422,
            code="language_not_allowed",
        )
    result = await openrouter_service.translate(payload.text, payload.language)
    return TranslationResponse(
        text=payload.text,
        translation=result.translation,
        source_language=result.source_language,
        target_language=payload.language,
    )
