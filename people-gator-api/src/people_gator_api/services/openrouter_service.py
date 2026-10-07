import json
from dataclasses import dataclass

from aiohttp import ClientSession, ClientTimeout

from people_gator_api.schemas.enums import Language
from people_gator_api.settings import OpenRouterSettings, settings
from logging import getLogger

logger = getLogger(__name__)

class OpenRouterError(RuntimeError):
    pass


@dataclass(slots=True)
class TranslationResult:
    translation: str
    source_language: Language


@dataclass(slots=True)
class HttpOpenRouterService:
    _cfg: OpenRouterSettings
    _session: ClientSession

    async def translate(
        self, text: str, target_language: Language
    ) -> TranslationResult:
        allowed = ", ".join(language.value for language in self._cfg.allowed_languages)
        system_prompt = (
            "You are a translation engine. Detect the source language of the given "
            'text, translate it into the requested target language, and reply with a '
            'single JSON object with exactly two keys: "translation" (the translated '
            f'text) and "source_language" (an ISO 639-1 code, one of: {allowed}). '
            "Reply with JSON only, no extra text or markdown."
        )
        user_prompt = f"Target language: {target_language.value}\nText: {text}"
        response = await self._session.post(
            f"{self._cfg.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._cfg.api_key}"},
            json={
                "model": self._cfg.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "response_format": {"type": "json_object"},
            },
        )
        raw_text = await response.text()
        if response.status >= 400:
            raise OpenRouterError(
                f"openrouter_http_error:{response.status}:{raw_text}"
            )
        try:
            payload = json.loads(raw_text)
            content = payload["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            translation = str(parsed["translation"])
            source_language = Language(parsed["source_language"])
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as exc:
            raise OpenRouterError("openrouter_invalid_response") from exc
        return TranslationResult(
            translation=translation, source_language=source_language
        )


_session: ClientSession | None = None
_service: HttpOpenRouterService | None = None


async def init_openrouter_service() -> None:
    global _session, _service  # noqa: PLW0603
    openrouter_settings = settings.openrouter
    if not openrouter_settings:
        logger.warning("OpenRouter API key is not configured.")
        return
    timeout = ClientTimeout(total=openrouter_settings.request_timeout_seconds)
    _session = ClientSession(timeout=timeout)
    _service = HttpOpenRouterService(openrouter_settings, _session)


async def close_openrouter_service() -> None:
    global _session, _service  # noqa: PLW0603
    if _session is not None:
        await _session.close()
    _session = None
    _service = None


def get_openrouter_service() -> HttpOpenRouterService:
    if _service is None:
        raise RuntimeError(
            "OpenRouter service is not initialised. "
            + "Ensure init_openrouter_service() has been awaited during startup."
        )
    return _service
