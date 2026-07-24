import json
from dataclasses import dataclass

from aiohttp import ClientResponse, ClientSession, ClientTimeout, FormData

from people_gator_api.services.embedding_service.schemas import (
    AllFacesResult,
    TextEmbeddingResponse,
    TimmImageEmbeddingResponse,
)
from people_gator_api.settings import EmbeddingServiceSettings, settings


class EmbeddingServiceError(RuntimeError):
    pass

@dataclass(slots=True)
class HttpEmbeddingModelService:
    _cfg: EmbeddingServiceSettings
    _session: ClientSession

    async def embed_face(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
    ) -> TimmImageEmbeddingResponse:
        form = FormData()
        form.add_field("file", image_bytes, filename=filename, content_type=content_type)
        response = await self._session.post(self._cfg.embed_image_url, data=form)
        payload = await self._read_json_text_or_raise(response)
        return TimmImageEmbeddingResponse.model_validate_json(payload)

    async def detect_and_embed_faces(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
    ) -> AllFacesResult:
        form = FormData()
        form.add_field("file", image_bytes, filename=filename, content_type=content_type)
        response = await self._session.post(self._cfg.detect_and_embed_image_url, data=form)
        payload = await self._read_json_text_or_raise(response)
        return AllFacesResult.model_validate_json(payload)

    async def embed_text(self, text: str) -> TextEmbeddingResponse:
        response = await self._session.post(
            self._cfg.embed_text_url,
            json={"text": text},
        )
        payload = await self._read_json_text_or_raise(response)
        return TextEmbeddingResponse.model_validate_json(payload)

    async def _read_json_text_or_raise(self, response: ClientResponse) -> str:
        raw_text = await response.text()
        if response.status >= 400:
            raise EmbeddingServiceError(
                f"embedding_service_http_error:{response.status}:{raw_text}"
            )
        try:
            json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise EmbeddingServiceError("embedding_service_invalid_json_response") from exc
        return raw_text


_session: ClientSession | None = None
_service: HttpEmbeddingModelService | None = None


async def init_embedding_service() -> None:
    global _session, _service  # noqa: PLW0603
    timeout = ClientTimeout(total=settings.embedding_service.request_timeout_seconds)
    _session = ClientSession(timeout=timeout)
    _service = HttpEmbeddingModelService(settings.embedding_service, _session)


async def close_embedding_service() -> None:
    global _session, _service  # noqa: PLW0603
    if _session is not None:
        await _session.close()
    _session = None
    _service = None


def get_embedding_service() -> HttpEmbeddingModelService:
    if _service is None:
        raise RuntimeError(
            "Embedding service is not initialised. "
            + "Ensure init_embedding_service() has been awaited during startup."
        )
    return _service
