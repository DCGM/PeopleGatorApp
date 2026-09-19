"""CRUD service for face annotations."""

import logging
import uuid
from collections.abc import AsyncGenerator

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.types import WeaviateField, WeaviateProperties

from people_gator_api.schemas.entities import (
    FaceCreateRequest,
    FaceListResponse,
    FaceResponse,
)
from people_gator_api.services.crud_services.source_resolution_service import (
    resolve_source_reference,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DEFAULT_FACE_VECTOR,
    FACE_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_face,
    reference_id_filter,
    single_named_vector_payload,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


def _face_properties(payload: FaceCreateRequest) -> WeaviateProperties:
    properties: dict[str, WeaviateField] = {
        "bounding_box": {
            "x": payload.bounding_box.x,
            "y": payload.bounding_box.y,
            "width": payload.bounding_box.width,
            "height": payload.bounding_box.height,
        },
        "keypoints": [
            {"type": item.type, "x": item.x, "y": item.y} for item in payload.keypoints
        ],
        "confidence": payload.confidence,
    }
    if payload.identifier is not None:
        properties["identifier"] = payload.identifier
    return properties


def _face_result(
    payload: FaceCreateRequest,
    *,
    detection_id: uuid.UUID,
    source_id: uuid.UUID,
    user_id: uuid.UUID,
) -> FaceResponse:
    return FaceResponse(
        detection_id=detection_id,
        identifier=payload.identifier,
        source_id=source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        user_id=user_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
    )


@trace()
async def create_face(
    client: WeaviateAsyncClient,
    payload: FaceCreateRequest,
    user_id: uuid.UUID,
) -> FaceResponse:
    source = await resolve_source_reference(
        client,
        source_id=payload.source_id,
        source=payload.source,
    )
    logger.info(
        "create_face called",
        extra={"source_id": source.source_id, "entity_id": payload.entity_id},
    )
    detection_id = new_uuid6()
    await client.collections.get(FACE_COLLECTION).data.insert(
        uuid=detection_id,
        properties=_face_properties(payload),
        references={
            "entity": payload.entity_id,
            "source": source.source_id,
            "user": user_id,
        },
        vector=single_named_vector_payload(DEFAULT_FACE_VECTOR, payload.embedding),
    )
    return _face_result(
        payload,
        detection_id=detection_id,
        source_id=source.source_id,
        user_id=user_id,
    )


@trace()
async def create_face_batch(
    client: WeaviateAsyncClient,
    payloads: AsyncGenerator[FaceCreateRequest, None],
    user_id: uuid.UUID,
) -> list[FaceResponse]:
    """Resolve sources and insert face detections as one streamed batch."""
    logger.info("create_face_batch called")
    collection = client.collections.use(FACE_COLLECTION)
    responses: list[FaceResponse] = []
    async with collection.batch.stream() as batch:
        async for payload in payloads:
            source = await resolve_source_reference(
                client,
                source_id=payload.source_id,
                source=payload.source,
            )
            detection_id = new_uuid6()
            await batch.add_object(
                uuid=detection_id,
                properties=_face_properties(payload),
                references={
                    "entity": payload.entity_id,
                    "source": source.source_id,
                    "user": user_id,
                },
                vector=single_named_vector_payload(
                    DEFAULT_FACE_VECTOR,
                    payload.embedding,
                ),
            )
            responses.append(
                _face_result(
                    payload,
                    detection_id=detection_id,
                    source_id=source.source_id,
                    user_id=user_id,
                )
            )
    logger.info("create_face_batch completed", extra={"count": len(responses)})
    return responses


@trace()
async def get_face(
    client: WeaviateAsyncClient,
    user_id: uuid.UUID,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    del user_id
    logger.debug("get_face called", extra={"detection_id": detection_id})
    response = await fetch_collection_object(
        client,
        FACE_COLLECTION,
        detection_id,
        reference_names=["user", "entity", "source"],
    )
    if response is None:
        logger.info("face not found", extra={"detection_id": detection_id})
        return None
    logger.debug("face found", extra={"detection_id": detection_id})
    return parse_face(
        response.properties,
        response.references,
        response.uuid,
    )


@trace()
async def patch_face_entity(
    client: WeaviateAsyncClient,
    user_id: uuid.UUID,
    detection_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> FaceResponse | None:
    del user_id
    logger.info(
        "patch_face_entity called",
        extra={"detection_id": detection_id, "entity_id": entity_id},
    )
    response = await fetch_collection_object(
        client,
        FACE_COLLECTION,
        detection_id,
        reference_names=["user", "entity", "source"],
    )
    if response is None:
        logger.info(
            "patch_face_entity skipped missing face",
            extra={"detection_id": detection_id},
        )
        return None

    current = parse_face(
        response.properties,
        response.references,
        response.uuid,
    )
    await client.collections.get(FACE_COLLECTION).data.reference_replace(
        from_uuid=detection_id,
        from_property="entity",
        to=entity_id,
    )
    logger.info(
        "patch_face_entity completed",
        extra={"detection_id": detection_id, "entity_id": entity_id},
    )
    return current.model_copy(update={"entity_id": entity_id})


@trace()
async def list_faces(
    client: WeaviateAsyncClient,
    user_id: uuid.UUID,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    owner_user_id: uuid.UUID | None = None,
) -> FaceListResponse:
    del user_id
    logger.debug(
        "list_faces called",
        extra={
            "source_id": source_id,
            "entity_id": entity_id,
            "after_id": after_id,
            "limit": limit,
            "owner_user_id": owner_user_id,
        },
    )
    filters: list[FilterReturn] = []
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))
    if owner_user_id is not None:
        filters.append(
            reference_id_filter(link_on="user", reference_id=owner_user_id)
        )
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        FACE_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["user", "entity", "source"]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_face(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in objects
        ],
        key=lambda item: item.detection_id,
    )
    logger.debug("list_faces completed", extra={"count": len(items)})
    return FaceListResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        after_id=items[-1].detection_id if len(items) == limit and items else None,
    )
