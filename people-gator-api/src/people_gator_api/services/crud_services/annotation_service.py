"""CRUD service for annotation entities."""

import logging
import uuid
from typing import TypeGuard

from weaviate import WeaviateAsyncClient
from weaviate.classes.data import DataObject
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import ReferenceInputs
from weaviate.collections.classes.types import WeaviateProperties

from people_gator_api.schemas.entities import (
    DocumentMentionCreateRequest,
    DocumentMentionListResponse,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceListResponse,
    FaceResponse,
    PageMentionCreateRequest,
    PageMentionListResponse,
    PageMentionResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DEFAULT_FACE_VECTOR,
    DOCUMENT_MENTION_COLLECTION,
    FACE_COLLECTION,
    PAGE_MENTION_COLLECTION,
)
from people_gator_api.services.crud_services.source_service import (
    resolve_source_reference,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    document_mention_response,
    empty_reference_queries,
    face_response,
    fetch_collection_page_with_total_count,
    page_mention_response,
    require_reference_uuid,
    reference_id_filter,
    single_named_vector_payload,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


def _is_flat_float_vector(
    value: list[float] | list[list[float]],
) -> TypeGuard[list[float]]:
    return all(isinstance(item, (int, float)) for item in value)


# ---------------------------------------------------------------------------
# Page Mentions
# ---------------------------------------------------------------------------


@trace()
async def create_page_mention(
    client: WeaviateAsyncClient,
    payload: PageMentionCreateRequest,
    principal_id: uuid.UUID,
) -> PageMentionResponse:
    source = await resolve_source_reference(
        client,
        principal_id,
        source_id=payload.source_id,
        source=payload.source,
    )
    logger.info(
        "create_page_mention called",
        extra={
            "source_id": source.source_id,
            "document_mention_id": payload.document_mention_id,
        },
    )
    page_mention_id = new_uuid6()
    await client.collections.get(PAGE_MENTION_COLLECTION).data.insert(
        uuid=page_mention_id,
        properties={
            "name": payload.name,
            "information": payload.information,
            "aliases": payload.aliases,
            "polygons": [
                {"points": [{"x": point.x, "y": point.y} for point in polygon.points]}
                for polygon in payload.polygons
            ],
        },
        references={
            "document_mention": payload.document_mention_id,
            "source": source.source_id,
            "principal": principal_id,
        },
    )
    return PageMentionResponse(
        page_mention_id=page_mention_id,
        name=payload.name,
        information=payload.information,
        aliases=payload.aliases,
        polygons=payload.polygons,
        document_mention_id=payload.document_mention_id,
        source_id=source.source_id,
        principal_id=principal_id,
    )


@trace()
async def create_many_page_mentions(
    client: WeaviateAsyncClient,
    payloads: list[PageMentionCreateRequest],
    principal_id: uuid.UUID,
) -> list[PageMentionResponse]:
    logger.info("create_many_page_mentions called", extra={"count": len(payloads)})
    if not payloads:
        return []
    collection = client.collections.get(PAGE_MENTION_COLLECTION)
    ids: list[uuid.UUID] = [new_uuid6() for _ in payloads]
    objects: list[DataObject[WeaviateProperties, ReferenceInputs]] = []
    for page_mention_id, payload in zip(ids, payloads):
        source_id = payload.source_id
        if source_id is None:
            raise ValueError("page mention source_id is required for batch insert")
        objects.append(
            DataObject(
                uuid=page_mention_id,
                properties={
                    "name": payload.name,
                    "information": payload.information,
                    "aliases": payload.aliases,
                    "polygons": [
                        {
                            "points": [
                                {"x": point.x, "y": point.y} for point in polygon.points
                            ]
                        }
                        for polygon in payload.polygons
                    ],
                },
                references={
                    "document_mention": payload.document_mention_id,
                    "source": source_id,
                    "principal": principal_id,
                },
            )
        )
    result = await collection.data.insert_many(objects)
    if result.errors:
        logger.error(
            "create_many_page_mentions partial failure",
            extra={"errors": {str(k): str(v) for k, v in result.errors.items()}},
        )
    responses: list[PageMentionResponse] = []
    for page_mention_id, payload in zip(ids, payloads):
        source_id = payload.source_id
        if source_id is None:
            raise ValueError("page mention source_id is required for batch response")
        responses.append(
            PageMentionResponse(
                page_mention_id=page_mention_id,
                name=payload.name,
                information=payload.information,
                aliases=payload.aliases,
                polygons=payload.polygons,
                document_mention_id=payload.document_mention_id,
                source_id=source_id,
                principal_id=principal_id,
            )
        )
    return responses


@trace()
async def get_page_mention(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    page_mention_id: uuid.UUID,
) -> PageMentionResponse | None:
    del principal_id
    logger.debug("get_page_mention called", extra={"page_mention_id": page_mention_id})
    response = await client.collections.get(
        PAGE_MENTION_COLLECTION
    ).query.fetch_object_by_id(
        page_mention_id,
        return_references=empty_reference_queries(
            ["principal", "document_mention", "source"]
        ),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "page_mention not found", extra={"page_mention_id": page_mention_id}
        )
        return None
    logger.debug("page_mention found", extra={"page_mention_id": page_mention_id})
    return page_mention_response(
        response.properties,
        response.references,
        response.uuid,
    )


@trace()
async def list_page_mentions(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    document_mention_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    owner_principal_id: uuid.UUID | None = None,
    name: str | None = None,
) -> PageMentionListResponse:
    del principal_id
    logger.debug(
        "list_page_mentions called",
        extra={
            "document_mention_id": document_mention_id,
            "source_id": source_id,
            "after_id": after_id,
            "limit": limit,
            "owner_principal_id": owner_principal_id,
            "name": name,
        },
    )
    filters: list[FilterReturn] = []
    if document_mention_id is not None:
        filters.append(
            reference_id_filter(
                link_on="document_mention", reference_id=document_mention_id
            )
        )
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if owner_principal_id is not None:
        filters.append(
            reference_id_filter(link_on="principal", reference_id=owner_principal_id)
        )
    if name is not None:
        filters.append(Filter.by_property("name").equal(name))
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        PAGE_MENTION_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(
            ["principal", "document_mention", "source"]
        ),
        after_id=after_id,
    )
    items = sorted(
        [
            page_mention_response(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in objects
        ],
        key=lambda item: item.page_mention_id,
    )
    return PageMentionListResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        after_id=items[-1].page_mention_id if len(items) == limit and items else None,
    )


# ---------------------------------------------------------------------------
# Document Mentions
# ---------------------------------------------------------------------------


@trace()
async def create_document_mention(
    client: WeaviateAsyncClient,
    payload: DocumentMentionCreateRequest,
    principal_id: uuid.UUID,
) -> DocumentMentionResponse:
    source = await resolve_source_reference(
        client,
        principal_id,
        source_id=payload.source_id,
        source=payload.source,
    )
    logger.info(
        "create_document_mention called",
        extra={"source_id": source.source_id, "entity_id": payload.entity_id},
    )
    document_mention_id = new_uuid6()
    await client.collections.get(DOCUMENT_MENTION_COLLECTION).data.insert(
        uuid=document_mention_id,
        properties={
            "name": payload.name,
            "information": payload.information,
            "aliases": payload.aliases,
        },
        references={
            "entity": payload.entity_id,
            "source": source.source_id,
            "principal": principal_id,
        },
    )
    dm_response = DocumentMentionResponse(
        document_mention_id=document_mention_id,
        name=payload.name,
        information=payload.information,
        aliases=payload.aliases,
        principal_id=principal_id,
        source_id=source.source_id,
        entity_id=payload.entity_id,
    )
    if payload.page_mentions:
        pm_payloads: list[PageMentionCreateRequest] = []
        for page_mention in payload.page_mentions:
            page_source = await resolve_source_reference(
                client,
                principal_id,
                source_id=page_mention.source_id,
                source=page_mention.source,
            )
            pm_payloads.append(
                PageMentionCreateRequest(
                    name=page_mention.name,
                    information=page_mention.information,
                    aliases=page_mention.aliases,
                    polygons=page_mention.polygons,
                    source_id=page_source.source_id,
                    document_mention_id=document_mention_id,
                )
            )
        await create_many_page_mentions(client, pm_payloads, principal_id)
    return dm_response


@trace()
async def get_document_mention(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    del principal_id
    logger.debug(
        "get_document_mention called",
        extra={"document_mention_id": document_mention_id},
    )
    response = await client.collections.get(
        DOCUMENT_MENTION_COLLECTION
    ).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "document_mention not found",
            extra={"document_mention_id": document_mention_id},
        )
        return None
    logger.debug(
        "document_mention found", extra={"document_mention_id": document_mention_id}
    )
    return document_mention_response(
        response.properties,
        response.references,
        response.uuid,
    )


@trace()
async def patch_document_mention_entity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    document_mention_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    del principal_id
    logger.info(
        "patch_document_mention_entity called",
        extra={"document_mention_id": document_mention_id, "entity_id": entity_id},
    )
    response = await client.collections.get(
        DOCUMENT_MENTION_COLLECTION
    ).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "patch_document_mention_entity skipped missing document_mention",
            extra={"document_mention_id": document_mention_id},
        )
        return None

    await client.collections.get(DOCUMENT_MENTION_COLLECTION).data.replace(
        uuid=document_mention_id,
        properties=dict(response.properties),
        references={
            "principal": require_reference_uuid(response.references, "principal"),
            "source": require_reference_uuid(response.references, "source"),
            "entity": entity_id,
        },
    )

    updated = await client.collections.get(
        DOCUMENT_MENTION_COLLECTION
    ).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if updated is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.warning(
            "patch_document_mention_entity could not read updated object",
            extra={"document_mention_id": document_mention_id},
        )
        return None
    logger.info(
        "patch_document_mention_entity completed",
        extra={"document_mention_id": document_mention_id, "entity_id": entity_id},
    )
    return document_mention_response(
        updated.properties,
        updated.references,
        updated.uuid,
    )


@trace()
async def list_document_mentions(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    entity_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    owner_principal_id: uuid.UUID | None = None,
    name: str | None = None,
) -> DocumentMentionListResponse:
    del principal_id
    logger.debug(
        "list_document_mentions called",
        extra={
            "entity_id": entity_id,
            "source_id": source_id,
            "after_id": after_id,
            "limit": limit,
            "owner_principal_id": owner_principal_id,
            "name": name,
        },
    )
    filters: list[FilterReturn] = []
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if owner_principal_id is not None:
        filters.append(
            reference_id_filter(link_on="principal", reference_id=owner_principal_id)
        )
    if name is not None:
        filters.append(Filter.by_property("name").equal(name))
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        DOCUMENT_MENTION_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
        after_id=after_id,
    )
    items = sorted(
        [
            document_mention_response(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in objects
        ],
        key=lambda item: item.document_mention_id,
    )
    return DocumentMentionListResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        after_id=items[-1].document_mention_id
        if len(items) == limit and items
        else None,
    )


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------


@trace()
async def create_face(
    client: WeaviateAsyncClient,
    payload: FaceCreateRequest,
    principal_id: uuid.UUID,
) -> FaceResponse:
    source = await resolve_source_reference(
        client,
        principal_id,
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
        properties={
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
        },
        references={
            "entity": payload.entity_id,
            "source": source.source_id,
            "principal": principal_id,
        },
        vector=single_named_vector_payload(DEFAULT_FACE_VECTOR, payload.embedding),
    )
    return FaceResponse(
        detection_id=detection_id,
        source_id=source.source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        principal_id=principal_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
    )


@trace()
async def get_face(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    del principal_id
    logger.debug("get_face called", extra={"detection_id": detection_id})
    response = await client.collections.get(FACE_COLLECTION).query.fetch_object_by_id(
        detection_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("face not found", extra={"detection_id": detection_id})
        return None
    logger.debug("face found", extra={"detection_id": detection_id})
    return face_response(
        response.properties,
        response.references,
        response.uuid,
    )


@trace()
async def patch_face_entity(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    detection_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> FaceResponse | None:
    del principal_id
    logger.info(
        "patch_face_entity called",
        extra={"detection_id": detection_id, "entity_id": entity_id},
    )
    response = await client.collections.get(FACE_COLLECTION).query.fetch_object_by_id(
        detection_id,
        include_vector=True,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "patch_face_entity skipped missing face",
            extra={"detection_id": detection_id},
        )
        return None

    vector_payload: dict[str, list[float]] | None = None
    named_vectors: dict[str, list[float]] = {}
    for vector_name, vector_value in response.vector.items():
        if _is_flat_float_vector(vector_value):
            named_vectors[vector_name] = [float(item) for item in vector_value]
    if named_vectors:
        vector_payload = named_vectors

    await client.collections.get(FACE_COLLECTION).data.replace(
        uuid=detection_id,
        properties=dict(response.properties),
        references={
            "principal": require_reference_uuid(response.references, "principal"),
            "source": require_reference_uuid(response.references, "source"),
            "entity": entity_id,
        },
        vector=vector_payload,
    )

    updated = await client.collections.get(FACE_COLLECTION).query.fetch_object_by_id(
        detection_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if updated is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.warning(
            "patch_face_entity could not read updated face",
            extra={"detection_id": detection_id},
        )
        return None
    logger.info(
        "patch_face_entity completed",
        extra={"detection_id": detection_id, "entity_id": entity_id},
    )
    return face_response(
        updated.properties,
        updated.references,
        updated.uuid,
    )


@trace()
async def list_faces(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
    *,
    owner_principal_id: uuid.UUID | None = None,
) -> FaceListResponse:
    del principal_id
    logger.debug(
        "list_faces called",
        extra={
            "source_id": source_id,
            "entity_id": entity_id,
            "after_id": after_id,
            "limit": limit,
            "owner_principal_id": owner_principal_id,
        },
    )
    filters: list[FilterReturn] = []
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))
    if owner_principal_id is not None:
        filters.append(
            reference_id_filter(link_on="principal", reference_id=owner_principal_id)
        )
    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        FACE_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
        after_id=after_id,
    )
    items = sorted(
        [
            face_response(
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
