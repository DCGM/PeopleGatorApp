"""CRUD service for annotation entities."""

import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import DescriptionCreateRequest
from people_gator_api.schemas.entities import DescriptionResponse
from people_gator_api.schemas.entities import DocumentMentionCreateRequest
from people_gator_api.schemas.entities import DocumentMentionResponse
from people_gator_api.schemas.entities import EntityNameCreateRequest
from people_gator_api.schemas.entities import EntityNameResponse
from people_gator_api.schemas.entities import FaceCreateRequest
from people_gator_api.schemas.entities import FaceResponse
from people_gator_api.schemas.entities import PageMentionCreateRequest
from people_gator_api.schemas.entities import PageMentionResponse
from people_gator_api.schemas.entities import SpanCreateRequest
from people_gator_api.schemas.entities import SpanResponse
from people_gator_api.services.vector_service.schema import DEFAULT_FACE_VECTOR
from people_gator_api.services.vector_service.schema import DEFAULT_FULLTEXT_VECTOR
from people_gator_api.services.vector_service.schema import DEFAULT_NAME_VECTOR
from people_gator_api.services.vector_service.schema import DESCRIPTION_COLLECTION
from people_gator_api.services.vector_service.schema import DOCUMENT_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import ENTITY_NAME_COLLECTION
from people_gator_api.services.vector_service.schema import FACE_COLLECTION
from people_gator_api.services.vector_service.schema import PAGE_MENTION_COLLECTION
from people_gator_api.services.vector_service.schema import SPAN_COLLECTION
from people_gator_api.services.weaviate_utils import combine_filters
from people_gator_api.services.weaviate_utils import description_response
from people_gator_api.services.weaviate_utils import document_mention_response
from people_gator_api.services.weaviate_utils import dual_named_vector_payload
from people_gator_api.services.weaviate_utils import entity_name_response
from people_gator_api.services.weaviate_utils import face_response
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import page_mention_response
from people_gator_api.services.weaviate_utils import query_objects
from people_gator_api.services.weaviate_utils import refresh_entity_aggregates
from people_gator_api.services.weaviate_utils import require_document_mention
from people_gator_api.services.weaviate_utils import require_page_mention
from people_gator_api.services.weaviate_utils import single_named_vector_payload
from people_gator_api.services.weaviate_utils import span_response
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


async def create_page_mention(
    client: WeaviateAsyncClient,
    payload: PageMentionCreateRequest,
) -> PageMentionResponse:
    document_mention = await require_document_mention(client, payload.document_mention_id)
    page_mention_id = new_uuid6()
    await upsert(
        client,
        PAGE_MENTION_COLLECTION,
        page_mention_id,
        properties={
            "page_mention_id": page_mention_id,
            "name": payload.name,
            "information": payload.information,
            "confidence": payload.confidence,
            "document_mention_id": payload.document_mention_id,
            "source_id": payload.source_id,
            "model_agent_id": payload.model_agent_id,
        },
        references={
            "document_mention": payload.document_mention_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=dual_named_vector_payload(
            name_embedding=payload.name_embedding,
            fulltext_embedding=payload.fulltext_embedding,
            name_vector_name=DEFAULT_NAME_VECTOR,
            fulltext_vector_name=DEFAULT_FULLTEXT_VECTOR,
        ),
    )
    await refresh_entity_aggregates(client, document_mention.entity_id)
    return PageMentionResponse(
        page_mention_id=page_mention_id,
        name=payload.name,
        information=payload.information,
        confidence=payload.confidence,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        model_agent_id=payload.model_agent_id,
    )


async def get_page_mention(
    client: WeaviateAsyncClient,
    page_mention_id: uuid.UUID,
) -> PageMentionResponse | None:
    obj = await fetch_by_id(
        client,
        PAGE_MENTION_COLLECTION,
        "page_mention_id",
        page_mention_id,
    )
    if obj is None:
        return None
    return page_mention_response(obj.properties)


async def list_page_mentions(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[PageMentionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if document_mention_id is not None:
        filters.append(
            Filter.by_property("document_mention_id").equal(str(document_mention_id))
        )
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(PAGE_MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [page_mention_response(item.properties) for item in objects],
        key=lambda item: item.page_mention_id,
    )
    if after_id is not None:
        items = [item for item in items if item.page_mention_id > after_id]
    return items[:limit]


async def create_span(
    client: WeaviateAsyncClient,
    payload: SpanCreateRequest,
) -> SpanResponse:
    page_mention = await require_page_mention(client, payload.page_mention_id)
    document_mention = await require_document_mention(client, page_mention.document_mention_id)
    span_id = new_uuid6()
    await upsert(
        client,
        SPAN_COLLECTION,
        span_id,
        properties={
            "span_id": span_id,
            "text": payload.text,
            "polygons": [
                {
                    "points": [{"x": point.x, "y": point.y} for point in polygon.points]
                }
                for polygon in payload.polygons
            ],
            "page_mention_id": payload.page_mention_id,
            "source_id": payload.source_id,
            "entity_id": document_mention.entity_id,
        },
        references={
            "page_mention": payload.page_mention_id,
            "source": payload.source_id,
            "entity": document_mention.entity_id,
        },
        vector=single_named_vector_payload(DEFAULT_NAME_VECTOR, payload.embedding),
    )
    return SpanResponse(
        span_id=span_id,
        text=payload.text,
        page_mention_id=payload.page_mention_id,
        source_id=payload.source_id,
        entity_id=document_mention.entity_id,
        polygons=payload.polygons,
    )


async def get_span(
    client: WeaviateAsyncClient,
    span_id: uuid.UUID,
) -> SpanResponse | None:
    obj = await fetch_by_id(client, SPAN_COLLECTION, "span_id", span_id)
    if obj is None:
        return None
    return span_response(obj.properties)


async def list_spans(
    client: WeaviateAsyncClient,
    page_mention_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[SpanResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if page_mention_id is not None:
        filters.append(Filter.by_property("page_mention_id").equal(str(page_mention_id)))
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(SPAN_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [span_response(item.properties) for item in objects],
        key=lambda item: item.span_id,
    )
    if after_id is not None:
        items = [item for item in items if item.span_id > after_id]
    return items[:limit]


async def create_document_mention(
    client: WeaviateAsyncClient,
    payload: DocumentMentionCreateRequest,
) -> DocumentMentionResponse:
    document_mention_id = new_uuid6()
    await upsert(
        client,
        DOCUMENT_MENTION_COLLECTION,
        document_mention_id,
        properties={
            "document_mention_id": document_mention_id,
            "name": payload.name,
            "information": payload.information,
            "model_agent_id": payload.model_agent_id,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=dual_named_vector_payload(
            name_embedding=payload.name_embedding,
            fulltext_embedding=payload.fulltext_embedding,
            name_vector_name=DEFAULT_NAME_VECTOR,
            fulltext_vector_name=DEFAULT_FULLTEXT_VECTOR,
        ),
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return DocumentMentionResponse(
        document_mention_id=document_mention_id,
        name=payload.name,
        information=payload.information,
        model_agent_id=payload.model_agent_id,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
    )


async def get_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    obj = await fetch_by_id(
        client,
        DOCUMENT_MENTION_COLLECTION,
        "document_mention_id",
        document_mention_id,
    )
    if obj is None:
        return None
    return document_mention_response(obj.properties)


async def list_document_mentions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DocumentMentionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [document_mention_response(item.properties) for item in objects],
        key=lambda item: item.document_mention_id,
    )
    if after_id is not None:
        items = [item for item in items if item.document_mention_id > after_id]
    return items[:limit]


async def create_face(
    client: WeaviateAsyncClient,
    payload: FaceCreateRequest,
) -> FaceResponse:
    detection_id = new_uuid6()
    await upsert(
        client,
        FACE_COLLECTION,
        detection_id,
        properties={
            "detection_id": detection_id,
            "bounding_box": {
                "x": payload.bounding_box.x,
                "y": payload.bounding_box.y,
                "width": payload.bounding_box.width,
                "height": payload.bounding_box.height,
            },
            "keypoints": [
                {"type": item.type, "x": item.x, "y": item.y}
                for item in payload.keypoints
            ],
            "confidence": payload.confidence,
            "source_id": payload.source_id,
            "model_agent_id": payload.model_agent_id,
            "entity_id": payload.entity_id,
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
            "model_agent": payload.model_agent_id,
        },
        vector=single_named_vector_payload(DEFAULT_FACE_VECTOR, payload.embedding),
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return FaceResponse(
        detection_id=detection_id,
        source_id=payload.source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        model_agent_id=payload.model_agent_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
    )


async def get_face(
    client: WeaviateAsyncClient,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    obj = await fetch_by_id(client, FACE_COLLECTION, "detection_id", detection_id)
    if obj is None:
        return None
    return face_response(obj.properties)


async def list_faces(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[FaceResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if source_id is not None:
        filters.append(Filter.by_property("source_id").equal(str(source_id)))
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(FACE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [face_response(item.properties) for item in objects],
        key=lambda item: item.detection_id,
    )
    if after_id is not None:
        items = [item for item in items if item.detection_id > after_id]
    return items[:limit]


async def create_description(
    client: WeaviateAsyncClient,
    payload: DescriptionCreateRequest,
) -> DescriptionResponse:
    description_id = new_uuid6()
    await upsert(
        client,
        DESCRIPTION_COLLECTION,
        description_id,
        properties={
            "description_id": description_id,
            "text": payload.text,
            "language": payload.language,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
        },
        references={"entity": payload.entity_id, "source": payload.source_id},
        vector=single_named_vector_payload(DEFAULT_FULLTEXT_VECTOR, payload.embedding),
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return DescriptionResponse(
        description_id=description_id,
        text=payload.text,
        language=payload.language,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
    )


async def get_description(
    client: WeaviateAsyncClient,
    description_id: uuid.UUID,
) -> DescriptionResponse | None:
    obj = await fetch_by_id(client, DESCRIPTION_COLLECTION, "description_id", description_id)
    if obj is None:
        return None
    return description_response(obj.properties)


async def list_descriptions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DescriptionResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(DESCRIPTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [description_response(item.properties) for item in objects],
        key=lambda item: item.description_id,
    )
    if after_id is not None:
        items = [item for item in items if item.description_id > after_id]
    return items[:limit]


async def create_entity_name(
    client: WeaviateAsyncClient,
    payload: EntityNameCreateRequest,
) -> EntityNameResponse:
    entity_name_id = new_uuid6()
    await upsert(
        client,
        ENTITY_NAME_COLLECTION,
        entity_name_id,
        properties={
            "entity_name_id": entity_name_id,
            "name": payload.name,
            "source_id": payload.source_id,
            "entity_id": payload.entity_id,
        },
        references={"entity": payload.entity_id, "source": payload.source_id},
        vector=single_named_vector_payload(DEFAULT_NAME_VECTOR, payload.embedding),
    )
    await refresh_entity_aggregates(client, payload.entity_id)
    return EntityNameResponse(
        entity_name_id=entity_name_id,
        name=payload.name,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
    )


async def get_entity_name(
    client: WeaviateAsyncClient,
    entity_name_id: uuid.UUID,
) -> EntityNameResponse | None:
    obj = await fetch_by_id(
        client,
        ENTITY_NAME_COLLECTION,
        "entity_name_id",
        entity_name_id,
    )
    if obj is None:
        return None
    return entity_name_response(obj.properties)


async def list_entity_names(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[EntityNameResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if entity_id is not None:
        filters.append(Filter.by_property("entity_id").equal(str(entity_id)))
    response = await client.collections.get(ENTITY_NAME_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [entity_name_response(item.properties) for item in objects],
        key=lambda item: item.entity_name_id,
    )
    if after_id is not None:
        items = [item for item in items if item.entity_name_id > after_id]
    return items[:limit]
