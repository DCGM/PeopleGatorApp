from typing import Protocol
from uuid import UUID

from people_gator_api.models.enums import AnnotationType
from people_gator_api.services.vector_service.schemas import (
    AnnotationSearchResult,
    EntitySearchResult,
)

DEFAULT_LIMIT = 10


class SearchAnnotationsByVector(Protocol):
    async def search_annotations_by_vector(
        self,
        vector: list[float],
        after_id: UUID | None = None,
        *,
        annotation_type: AnnotationType | None = None,
        entity_id: UUID | None = None,
        limit: int = DEFAULT_LIMIT,
        certainty: float | None = None,
        distance: float | None = None,
    ) -> list[AnnotationSearchResult]:
        ...


class SearchIdentitiesByVector(Protocol):
    async def search_identities_by_vector(
        self,
        vector: list[float],
        *,
        limit: int = DEFAULT_LIMIT,
        face_distance: float | None = None,
        name_distance: float | None = None,
        combined_distance: float | None = None,
    ) -> list[EntitySearchResult]:
        ...


class VectorSearchServiceProtocol(SearchAnnotationsByVector, SearchIdentitiesByVector):
    """Protocol for a service that can perform vector similarity search over annotation and identity data."""
    pass