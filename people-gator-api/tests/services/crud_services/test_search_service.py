from __future__ import annotations

import os
import uuid

from people_gator_api.schemas.enums import AnnotationType
from people_gator_api.services.vector_service.schemas import AnnotationSearchResult

os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_SECURE", "false")

from people_gator_api.services.crud_services import search_service
from people_gator_api.settings import SearchEntityAggregationMode


def _annotation_result(
    *,
    entity_id: uuid.UUID | None = None,
    annotation_id: uuid.UUID | None = None,
    distance: float | None = None,
) -> AnnotationSearchResult:
    return AnnotationSearchResult(
        weaviate_id=uuid.uuid4(),
        annotation_type=AnnotationType.face,
        annotation_id=annotation_id or uuid.uuid4(),
        source_id=uuid.uuid4(),
        model_agent_id=None,
        confidence=None,
        entity_id=entity_id,
        distance=distance,
        certainty=None,
    )


def test_aggregate_entity_scores_supports_best_and_average_modes() -> None:
    entity_id = uuid.uuid4()
    hits = [
        _annotation_result(entity_id=entity_id, distance=0.1),
        _annotation_result(entity_id=entity_id, distance=0.4),
    ]

    best_scores = search_service.aggregate_entity_scores(
        hits,
        SearchEntityAggregationMode.best_annotation,
    )
    average_scores = search_service.aggregate_entity_scores(
        hits,
        SearchEntityAggregationMode.average_annotation,
    )

    assert best_scores == {entity_id: 0.9}
    assert average_scores == {entity_id: 0.75}


def test_aggregate_annotation_hits_keeps_best_hit_per_annotation() -> None:
    shared_annotation_id = uuid.uuid4()
    better_hit = _annotation_result(annotation_id=shared_annotation_id, distance=0.1)
    weaker_hit = _annotation_result(annotation_id=shared_annotation_id, distance=0.3)

    aggregated = search_service.aggregate_annotation_hits([better_hit, weaker_hit])

    assert aggregated[(AnnotationType.face, shared_annotation_id)].hit == better_hit
    assert aggregated[(AnnotationType.face, shared_annotation_id)].score == 0.9
