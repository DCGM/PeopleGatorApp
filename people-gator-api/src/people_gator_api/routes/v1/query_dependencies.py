"""Typed dependencies for list and search query-string parameters.

The schemas remain transport-neutral while this module owns the HTTP naming
convention: search inputs use ``query.<field>``, filters use
``filter.<field>``, and pagination fields remain at the top level.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
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
    EntityLinkState,
    ScoreAggregation,
    ScoreFusion,
    SourceKind,
)
from people_gator_api.schemas.faces import FaceListFilter
from people_gator_api.schemas.mentions import TextMentionListFilter
from people_gator_api.schemas.search import QueryBase
from people_gator_api.schemas.sorting import (
    RELEVANCE,
    DocumentSortField,
    EntitySortField,
    FaceSortField,
    PageSortField,
    SortDirection,
    SortableRequest,
    TextMentionGroupSortField,
    TextMentionSortField,
)
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
    try:
        return model.model_validate(
            {name: value for name, value in values.items() if value is not None}
        )
    except ValueError as exc:
        raise_api_error(422, "invalid_filter", str(exc))


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
        str,
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
    evidence_library: Annotated[list[str] | None, _model_parameter(EntityListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "evidence_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(EntityListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(EntityListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(EntityListFilter, "entity_link_state", "filter")] = None,
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
    last_touched_from: Annotated[datetime | None, _model_parameter(EntityListFilter, "last_touched_from", "filter")] = None,
    last_touched_to: Annotated[datetime | None, _model_parameter(EntityListFilter, "last_touched_to", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "document_source_id", "filter")] = None,
    last_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "last_touched_by_user_id", "filter")] = None,
    last_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(EntityListFilter, "last_touched_by_api_key_id", "filter")] = None,
) -> EntityListFilter:
    return _filter(
        EntityListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        entity_link_state=entity_link_state,
        entity_id=entity_id,
        entity_type=entity_type,
        last_touched_from=last_touched_from,
        last_touched_to=last_touched_to,
        document_source_id=document_source_id,
        last_touched_by_user_id=last_touched_by_user_id,
        last_touched_by_api_key_id=last_touched_by_api_key_id,

        wikidata_id=wikidata_id,
        nlcr_authority_id=nlcr_authority_id,
        source_id=source_id,
        detection_id=detection_id,
        mention_id=mention_id,
        has_mentions=has_mentions,
        has_detections=has_detections,
    )


def face_list_filter_dependency(
    evidence_library: Annotated[list[str] | None, _model_parameter(FaceListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(FaceListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(FaceListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(FaceListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(FaceListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(FaceListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(FaceListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(FaceListFilter, "entity_link_state", "filter")] = None,
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
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        entity_link_state=entity_link_state,
        entity_id=entity_id,
        source_id=source_id,
        detection_id=detection_id,
    )


def text_mention_list_filter_dependency(
    evidence_library: Annotated[list[str] | None, _model_parameter(TextMentionListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(TextMentionListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(TextMentionListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(TextMentionListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(TextMentionListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(TextMentionListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(TextMentionListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(TextMentionListFilter, "entity_link_state", "filter")] = None,
    entity_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(TextMentionListFilter, "entity_id", "filter"),
    ] = None,
    source_id: Annotated[
        list[uuid.UUID] | None,
        _model_parameter(TextMentionListFilter, "source_id", "filter"),
    ] = None,
    name: Annotated[
        list[str] | None,
        _model_parameter(TextMentionListFilter, "name", "filter"),
    ] = None,
) -> TextMentionListFilter:
    return _filter(
        TextMentionListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        entity_link_state=entity_link_state,
        entity_id=entity_id,
        source_id=source_id,
        name=name,
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
    evidence_library: Annotated[list[str] | None, _model_parameter(SourceListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(SourceListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(SourceListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(SourceListFilter, "entity_link_state", "filter")] = None,
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
    last_touched_from: Annotated[datetime | None, _model_parameter(SourceListFilter, "last_touched_from", "filter")] = None,
    last_touched_to: Annotated[datetime | None, _model_parameter(SourceListFilter, "last_touched_to", "filter")] = None,
    last_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "last_touched_by_user_id", "filter")] = None,
    last_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(SourceListFilter, "last_touched_by_api_key_id", "filter")] = None,
) -> SourceListFilter:
    return _filter(
        SourceListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        last_touched_from=last_touched_from,
        last_touched_to=last_touched_to,
        last_touched_by_user_id=last_touched_by_user_id,
        last_touched_by_api_key_id=last_touched_by_api_key_id,

        entity_link_state=entity_link_state,
        source_type=source_type,
        url=url,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


def page_list_filter_dependency(
    evidence_library: Annotated[list[str] | None, _model_parameter(PageListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(PageListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(PageListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(PageListFilter, "entity_link_state", "filter")] = None,
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
    has_mentions: Annotated[
        bool | None,
        _model_parameter(PageListFilter, "has_mentions", "filter"),
    ] = None,
    has_faces: Annotated[
        bool | None,
        _model_parameter(PageListFilter, "has_faces", "filter"),
    ] = None,
    has_entities: Annotated[
        bool | None,
        _model_parameter(PageListFilter, "has_entities", "filter"),
    ] = None,
    last_touched_from: Annotated[datetime | None, _model_parameter(PageListFilter, "last_touched_from", "filter")] = None,
    last_touched_to: Annotated[datetime | None, _model_parameter(PageListFilter, "last_touched_to", "filter")] = None,
    last_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "last_touched_by_user_id", "filter")] = None,
    last_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(PageListFilter, "last_touched_by_api_key_id", "filter")] = None,
) -> PageListFilter:
    return _filter(
        PageListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        last_touched_from=last_touched_from,
        last_touched_to=last_touched_to,
        last_touched_by_user_id=last_touched_by_user_id,
        last_touched_by_api_key_id=last_touched_by_api_key_id,

        entity_link_state=entity_link_state,
        url=url,
        library=library,
        document_id=document_id,
        page_id=page_id,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
        has_mentions=has_mentions,
        has_faces=has_faces,
        has_entities=has_entities,
    )


def document_list_filter_dependency(
    evidence_library: Annotated[list[str] | None, _model_parameter(DocumentListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(DocumentListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(DocumentListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(DocumentListFilter, "entity_link_state", "filter")] = None,
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
    last_touched_from: Annotated[datetime | None, _model_parameter(DocumentListFilter, "last_touched_from", "filter")] = None,
    last_touched_to: Annotated[datetime | None, _model_parameter(DocumentListFilter, "last_touched_to", "filter")] = None,
    last_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "last_touched_by_user_id", "filter")] = None,
    last_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(DocumentListFilter, "last_touched_by_api_key_id", "filter")] = None,
    has_unassigned_faces: Annotated[bool | None, _model_parameter(DocumentListFilter, "has_unassigned_faces", "filter")] = None,
) -> DocumentListFilter:
    return _filter(
        DocumentListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        last_touched_from=last_touched_from,
        last_touched_to=last_touched_to,
        last_touched_by_user_id=last_touched_by_user_id,
        last_touched_by_api_key_id=last_touched_by_api_key_id,
        has_unassigned_faces=has_unassigned_faces,

        entity_link_state=entity_link_state,
        url=url,
        library=library,
        document_id=document_id,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


def image_list_filter_dependency(
    evidence_library: Annotated[list[str] | None, _model_parameter(ImageListFilter, "evidence_library", "filter")] = None,
    evidence_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "evidence_source_id", "filter")] = None,
    document_source_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "document_source_id", "filter")] = None,
    evidence_touched_from: Annotated[datetime | None, _model_parameter(ImageListFilter, "evidence_touched_from", "filter")] = None,
    evidence_touched_to: Annotated[datetime | None, _model_parameter(ImageListFilter, "evidence_touched_to", "filter")] = None,
    evidence_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "evidence_touched_by_user_id", "filter")] = None,
    evidence_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "evidence_touched_by_api_key_id", "filter")] = None,
    entity_link_state: Annotated[list[EntityLinkState] | None, _model_parameter(ImageListFilter, "entity_link_state", "filter")] = None,
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
    last_touched_from: Annotated[datetime | None, _model_parameter(ImageListFilter, "last_touched_from", "filter")] = None,
    last_touched_to: Annotated[datetime | None, _model_parameter(ImageListFilter, "last_touched_to", "filter")] = None,
    last_touched_by_user_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "last_touched_by_user_id", "filter")] = None,
    last_touched_by_api_key_id: Annotated[list[uuid.UUID] | None, _model_parameter(ImageListFilter, "last_touched_by_api_key_id", "filter")] = None,
) -> ImageListFilter:
    return _filter(
        ImageListFilter,
        evidence_library=evidence_library,
        evidence_source_id=evidence_source_id,
        document_source_id=document_source_id,
        evidence_touched_from=evidence_touched_from,
        evidence_touched_to=evidence_touched_to,
        evidence_touched_by_user_id=evidence_touched_by_user_id,
        evidence_touched_by_api_key_id=evidence_touched_by_api_key_id,
        last_touched_from=last_touched_from,
        last_touched_to=last_touched_to,
        last_touched_by_user_id=last_touched_by_user_id,
        last_touched_by_api_key_id=last_touched_by_api_key_id,

        entity_link_state=entity_link_state,
        url=url,
        source_id=source_id,
        entity_id=entity_id,
        detection_id=detection_id,
        mention_id=mention_id,
    )


@dataclass(frozen=True)
class SortParameters:
    """Validated by the resource request schema; None keeps its default order."""

    sort: str | None = None
    sort_direction: SortDirection | None = None


DEFAULT_SORT = SortParameters()


def _list_fields(fields: type[StrEnum], name: str) -> type[StrEnum]:
    """The fields of a list endpoint: relevance requires a search score."""
    return StrEnum(name, {item.name: item.value for item in fields if item.value != RELEVANCE})


def _sort_dependency(fields: type[StrEnum]):
    def dependency(
        sort: Annotated[
            fields | None,  # type: ignore[valid-type]
            Query(description=SortableRequest.model_fields["sort"].description),
        ] = None,
        sort_direction: Annotated[
            SortDirection | None,
            Query(description=SortableRequest.model_fields["sort_direction"].description),
        ] = None,
    ) -> SortParameters:
        return SortParameters(
            sort=sort.value if sort is not None else None,
            sort_direction=sort_direction,
        )

    return dependency


EntityListSortField = _list_fields(EntitySortField, "EntityListSortField")
DocumentListSortField = _list_fields(DocumentSortField, "DocumentListSortField")
PageListSortField = _list_fields(PageSortField, "PageListSortField")
FaceListSortField = _list_fields(FaceSortField, "FaceListSortField")

EntityListSortDependency = Annotated[SortParameters, Depends(_sort_dependency(EntityListSortField))]
EntitySearchSortDependency = Annotated[SortParameters, Depends(_sort_dependency(EntitySortField))]
DocumentListSortDependency = Annotated[SortParameters, Depends(_sort_dependency(DocumentListSortField))]
DocumentSearchSortDependency = Annotated[SortParameters, Depends(_sort_dependency(DocumentSortField))]
PageListSortDependency = Annotated[SortParameters, Depends(_sort_dependency(PageListSortField))]
PageSearchSortDependency = Annotated[SortParameters, Depends(_sort_dependency(PageSortField))]
FaceListSortDependency = Annotated[SortParameters, Depends(_sort_dependency(FaceListSortField))]
FaceSearchSortDependency = Annotated[SortParameters, Depends(_sort_dependency(FaceSortField))]
TextMentionSortDependency = Annotated[SortParameters, Depends(_sort_dependency(TextMentionSortField))]
TextMentionGroupSortDependency = Annotated[
    SortParameters, Depends(_sort_dependency(TextMentionGroupSortField))
]


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
    "DEFAULT_SORT",
    "DocumentListSortDependency",
    "DocumentSearchSortDependency",
    "EntityListSortDependency",
    "EntitySearchSortDependency",
    "FaceListSortDependency",
    "FaceSearchSortDependency",
    "PageListSortDependency",
    "PageSearchSortDependency",
    "SortParameters",
    "TextMentionGroupSortDependency",
    "TextMentionSortDependency",
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
