from typing import Protocol

from people_gator_api.services.embedding_service.schemas import (
    AllFacesResult,
    TextEmbeddingResponse,
    TimmImageEmbeddingResponse,
)


class ImageEmbeddingModel(Protocol):
    async def embed_face(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
    ) -> TimmImageEmbeddingResponse:
        ...


class ImageDetectionEmbeddingModel(Protocol):
    async def detect_and_embed_faces(
        self,
        image_bytes: bytes,
        *,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg",
    ) -> AllFacesResult:
        ...


class TextEmbeddingModel(Protocol):
    async def embed_text(self, text: str) -> TextEmbeddingResponse:
        ...


class EmbeddingModelService(
    ImageEmbeddingModel,
    ImageDetectionEmbeddingModel,
    TextEmbeddingModel,
    Protocol,
):
    ...
