"""Typed dependencies for list and search query-string parameters.

The schemas remain transport-neutral while this module owns the HTTP naming
convention: search inputs use ``query.<field>``, filters use
``filter.<field>``, and pagination fields remain at the top level.
"""

import uuid
from typing import Annotated, Any

from fastapi import Depends, Query
from pydantic import AnyUrl, BaseModel

from people_gator_api.schemas.common import (
    GenericListRequest,
    ListFilterBase,
)
from people_gator_api.schemas.entities import EntityListFilter
from people_gator_api.schemas.enums import (
    DEFAULT_FACE_EMBEDDING_MODEL,
    EntityType,
    FaceEmbeddingModel,
    ScoreAggregation,
    ScoreFusion,
    SourceKind,
)
from people_gator_api.schemas.faces import FaceListFilter
from people_gator_api.schemas.mentions import TextMentionListFilter
from people_gator_api.schemas.search import QueryBase
from people_gator_api.schemas.sources import (
    DocumentListFilter,
    ImageListFilter,
    PageListFilter,
    SourceListFilter,
)
from people_gator_api.schemas.users import UserListFilter
from people_gator_api.utils.http_errors import raise_api_error


def _model_parameter(
    model: type[BaseModel],
    field_name: str,
    prefix: str,
) -> Any:
    """Describe one namespaced model field as a FastAPI query parameter."""
    return Query(
        alias=f"{prefix}.{field_name}",
        description=model.model_fields[field_name].description,
    )


def _filter[T: ListFilterBase](
    model: type[T],
    **values: object,
) -> T:
    """Build a filter without turning absent query parameters into nulls."""
    return model.model_validate(
        {name: value for name, value in values.items() if value is not None}
    )


def list_request_dependency(
    limit: Annotated[
        int,
        Query(
            ge=0,
            description=GenericListRequest.model_fields["limit"].description,
        ),
    ] = 50,
    return_total_count: Annotated[
        bool,
        Query(
            description=GenericListRequest.model_fields[
                "return_total_count"
            ].description,
        ),
    ] = False,
    cursor: Annotated[
        str | None,
        Query(description=GenericListRequest.model_fields["cursor"].description),
    ] = None,
) -> GenericListRequest:
    """Parse pagination for ordinary list endpoints."""
    return GenericListRequest(
        limit=limit,
        return_total_count=return_total_count,
        cursor=cursor,
    )


def search_list_request_dependency(
    limit: Annotated[
        int,
        Query(
            ge=0,
            description=GenericListRequest.model_fields["limit"].description,
        ),
    ] = 20,
    return_total_count: Annotated[
        bool,
        Query(
            description=GenericListRequest.model_fields[
                "return_total_count"
            ].description,
        ),
    ] = False,
    cursor: Annotated[
        str | None,
        Query(description=GenericListRequest.model_fields["cursor"].description),
    ] = None,
) -> GenericListRequest:
    """Parse pagination for search endpoints while retaining their page size."""
    return GenericListRequest(
        limit=limit,
        return_total_count=return_total_count,
        cursor=cursor,
    )


def search_query_dependency(
    text: Annotated[
        list[str] | None,
        _model_parameter(QueryBase, "text", "query"),
    ] = None,
    face_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(QueryBase, "face_id", "query"),
    ] = None,
    face_embedding_model: Annotated[
        FaceEmbeddingModel,
        _model_parameter(QueryBase, "face_embedding_model", "query"),
    ] = DEFAULT_FACE_EMBEDDING_MODEL,
    exclude_reference_face_id: Annotated[
        bool,
        _model_parameter(QueryBase, "exclude_reference_face_id", "query"),
    ] = True,
    score_aggregation: Annotated[
        ScoreAggregation,
        _model_parameter(QueryBase, "score_aggregation", "query"),
    ] = ScoreAggregation.min,
    score_fusion: Annotated[
        ScoreFusion,
        _model_parameter(QueryBase, "score_fusion", "query"),
    ] = ScoreFusion.rrf,
) -> QueryBase:
    """Parse and validate the multimodal part of a search request."""
    values: dict[str, object] = {
        "face_embedding_model": face_embedding_model,
        "exclude_reference_face_id": exclude_reference_face_id,
        "score_aggregation": score_aggregation,
        "score_fusion": score_fusion,
    }
    if text is not None:
        values["text"] = text
    if face_id is not None:
        values["face_id"] = face_id

    try:
        return QueryBase.model_validate(values)
    except ValueError as exc:
        raise_api_error(422, "invalid_search", str(exc))


def entity_list_filter_dependency(
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(EntityListFilter, "entity_id", "filter"),
    ] = None,
    entity_type: Annotated[
        list[EntityType] | None,
        _model_parameter(EntityListFilter, "entity_type", "filter"),
    ] = None,
    wikidata_id: Annotated[
        list[str] | None,
        _model_parameter(EntityListFilter, "wikidata_id", "filter"),
    ] = None,
    nlcr_authority_id: Annotated[
        list[str] | None,
        _model_parameter(EntityListFilter, "nlcr_authority_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(EntityListFilter, "source_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(EntityListFilter, "detection_id", "filter"),
    ] = None,
    mention_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(EntityListFilter, "mention_id", "filter"),
    ] = None,
    has_mentions: Annotated[
        bool | None,
        _model_parameter(EntityListFilter, "has_mentions", "filter"),
    ] = None,
    has_detections: Annotated[
        bool | None,
        _model_parameter(EntityListFilter, "has_detections", "filter"),
    ] = None,
) -> EntityListFilter:
    return _filter(
        EntityListFilter,
        entity_id=entity_id,
        entity_type=entity_type,
        wikidata_id=wikidata_id,
        nlcr_authority_id=nlcr_authority_id,
        source_id=source_id,
        detection_id=detection_id,
        mention_id=mention_id,
        has_mentions=has_mentions,
        has_detections=has_detections,
    )


def face_list_filter_dependency(
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(FaceListFilter, "entity_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(FaceListFilter, "source_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(FaceListFilter, "detection_id", "filter"),
    ] = None,
) -> FaceListFilter:
    return _filter(
        FaceListFilter,
        entity_id=entity_id,
        source_id=source_id,
        detection_id=detection_id,
    )


def text_mention_list_filter_dependency(
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(TextMentionListFilter, "entity_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(TextMentionListFilter, "source_id", "filter"),
    ] = None,
) -> TextMentionListFilter:
    return _filter(
        TextMentionListFilter,
        entity_id=entity_id,
        source_id=source_id,
    )


def user_list_filter_dependency(
    display_name: Annotated[
        list[str] | None,
        _model_parameter(UserListFilter, "display_name", "filter"),
    ] = None,
    is_active: Annotated[
        list[bool] | None,
        _model_parameter(UserListFilter, "is_active", "filter"),
    ] = None,
    external_subject: Annotated[
        list[str] | None,
        _model_parameter(UserListFilter, "external_subject", "filter"),
    ] = None,
    external_issuer: Annotated[
        list[str] | None,
        _model_parameter(UserListFilter, "external_issuer", "filter"),
    ] = None,
    email: Annotated[
        list[str] | None,
        _model_parameter(UserListFilter, "email", "filter"),
    ] = None,
) -> UserListFilter:
    return _filter(
        UserListFilter,
        display_name=display_name,
        is_active=is_active,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=email,
    )


def source_list_filter_dependency(
    source_type: Annotated[
        list[SourceKind] | None,
        _model_parameter(SourceListFilter, "source_type", "filter"),
    ] = None,
    url: Annotated[
        list[AnyUrl] | None,
        _model_parameter(SourceListFilter, "url", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(SourceListFilter, "source_id", "filter"),
    ] = None,
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(SourceListFilter, "entity_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(SourceListFilter, "detection_id", "filter"),
    ] = None,
    mention_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(SourceListFilter, "mention_id", "filter"),
    ] = None,
) -> SourceListFilter:
    return _filter(
        SourceListFilter,
        source_type=source_type,
        url=url,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


def page_list_filter_dependency(
    url: Annotated[
        list[AnyUrl] | None,
        _model_parameter(PageListFilter, "url", "filter"),
    ] = None,
    library: Annotated[
        list[str] | None,
        _model_parameter(PageListFilter, "library", "filter"),
    ] = None,
    document_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "document_id", "filter"),
    ] = None,
    page_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "page_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "source_id", "filter"),
    ] = None,
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "entity_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "detection_id", "filter"),
    ] = None,
    mention_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(PageListFilter, "mention_id", "filter"),
    ] = None,
) -> PageListFilter:
    return _filter(
        PageListFilter,
        url=url,
        library=library,
        document_id=document_id,
        page_id=page_id,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


def document_list_filter_dependency(
    url: Annotated[
        list[AnyUrl] | None,
        _model_parameter(DocumentListFilter, "url", "filter"),
    ] = None,
    library: Annotated[
        list[str] | None,
        _model_parameter(DocumentListFilter, "library", "filter"),
    ] = None,
    document_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(DocumentListFilter, "document_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(DocumentListFilter, "source_id", "filter"),
    ] = None,
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(DocumentListFilter, "entity_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(DocumentListFilter, "detection_id", "filter"),
    ] = None,
    mention_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(DocumentListFilter, "mention_id", "filter"),
    ] = None,
) -> DocumentListFilter:
    return _filter(
        DocumentListFilter,
        url=url,
        library=library,
        document_id=document_id,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


def image_list_filter_dependency(
    url: Annotated[
        list[AnyUrl] | None,
        _model_parameter(ImageListFilter, "url", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(ImageListFilter, "source_id", "filter"),
    ] = None,
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(ImageListFilter, "entity_id", "filter"),
    ] = None,
    detection_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(ImageListFilter, "detection_id", "filter"),
    ] = None,
    mention_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(ImageListFilter, "mention_id", "filter"),
    ] = None,
) -> ImageListFilter:
    return _filter(
        ImageListFilter,
        url=url,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


ListRequestDependency = Annotated[
    GenericListRequest,
    Depends(list_request_dependency),
]
SearchListRequestDependency = Annotated[
    GenericListRequest,
    Depends(search_list_request_dependency),
]
SearchQueryDependency = Annotated[QueryBase, Depends(search_query_dependency)]
EntityListFilterDependency = Annotated[
    EntityListFilter,
    Depends(entity_list_filter_dependency),
]
FaceListFilterDependency = Annotated[
    FaceListFilter,
    Depends(face_list_filter_dependency),
]
TextMentionListFilterDependency = Annotated[
    TextMentionListFilter,
    Depends(text_mention_list_filter_dependency),
]
UserListFilterDependency = Annotated[
    UserListFilter,
    Depends(user_list_filter_dependency),
]
SourceListFilterDependency = Annotated[
    SourceListFilter,
    Depends(source_list_filter_dependency),
]
PageListFilterDependency = Annotated[
    PageListFilter,
    Depends(page_list_filter_dependency),
]
DocumentListFilterDependency = Annotated[
    DocumentListFilter,
    Depends(document_list_filter_dependency),
]
ImageListFilterDependency = Annotated[
    ImageListFilter,
    Depends(image_list_filter_dependency),
]


__all__ = [
    "DocumentListFilterDependency",
    "EntityListFilterDependency",
    "FaceListFilterDependency",
    "ImageListFilterDependency",
    "ListRequestDependency",
    "PageListFilterDependency",
    "SearchListRequestDependency",
    "SearchQueryDependency",
    "SourceListFilterDependency",
    "TextMentionListFilterDependency",
    "UserListFilterDependency",
]
