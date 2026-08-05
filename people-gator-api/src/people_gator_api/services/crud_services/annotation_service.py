"""CRUD service for annotation entities."""

import uuid
from typing import TypeGuard

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.entities import (
    DocumentMentionCreateRequest,
    DocumentMentionResponse,
    FaceCreateRequest,
    FaceResponse,
    PageMentionCreateRequest,
    PageMentionResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    DEFAULT_FACE_VECTOR,
    DOCUMENT_MENTION_COLLECTION,
    FACE_COLLECTION,
    PAGE_MENTION_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    document_mention_response,
    empty_reference_queries,
    face_response,
    page_mention_response,
    require_reference_uuid,
    reference_id_filter,
    single_named_vector_payload,
    upsert,
)
from people_gator_api.utils.uuid_utils import new_uuid6


def _is_flat_float_vector(value: list[float] | list[list[float]]) -> TypeGuard[list[float]]:
    return all(isinstance(item, (int, float)) for item in value)


# ---------------------------------------------------------------------------
# Page Mentions
# ---------------------------------------------------------------------------


async def create_page_mention(
    client: WeaviateAsyncClient,
    payload: PageMentionCreateRequest,
) -> PageMentionResponse:
    page_mention_id = new_uuid6()
    await upsert(
        client,
        PAGE_MENTION_COLLECTION,
        page_mention_id,
        properties={
            "name": payload.name,
            "information": payload.information,
            "aliases": [{"alias": alias} for alias in payload.aliases],
            "polygons": [
                {
                    "points": [
                        {"x": point.x, "y": point.y}
                        for point in polygon.points
                    ]
                }
                for polygon in payload.polygons
            ],
        },
        references={
            "document_mention": payload.document_mention_id,
            "source": payload.source_id,
            "principal": payload.principal_id,
        },
    )
    return PageMentionResponse(
        page_mention_id=page_mention_id,
        name=payload.name,
        information=payload.information,
        aliases=payload.aliases,
        polygons=payload.polygons,
        document_mention_id=payload.document_mention_id,
        source_id=payload.source_id,
        principal_id=payload.principal_id,
    )


async def get_page_mention(
    client: WeaviateAsyncClient,
    page_mention_id: uuid.UUID,
) -> PageMentionResponse | None:
    response = await client.collections.get(PAGE_MENTION_COLLECTION).query.fetch_object_by_id(
        page_mention_id,
        return_references=empty_reference_queries(["principal", "document_mention", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return page_mention_response(
        response.properties,
        response.references,
        response.uuid,
    )


async def list_page_mentions(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[PageMentionResponse]:
    filters: list[FilterReturn] = []
    if document_mention_id is not None:
        filters.append(reference_id_filter(link_on="document_mention", reference_id=document_mention_id))
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    response = await client.collections.get(PAGE_MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal", "document_mention", "source"]),
        after=after_id
    )
    items = sorted(
        [
            page_mention_response(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in response.objects
        ],
        key=lambda item: item.page_mention_id,
    )
    return items

# ---------------------------------------------------------------------------
# Document Mentions
# ---------------------------------------------------------------------------


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
            "name": payload.name,
            "information": payload.information,
            "aliases": [{"alias": alias} for alias in payload.aliases],
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
            "principal": payload.principal_id,
        },
    )
    return DocumentMentionResponse(
        document_mention_id=document_mention_id,
        name=payload.name,
        information=payload.information,
        aliases=payload.aliases,
        principal_id=payload.principal_id,
        source_id=payload.source_id,
        entity_id=payload.entity_id,
    )


async def get_document_mention(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return document_mention_response(
        response.properties,
        response.references,
        response.uuid,
    )


async def patch_document_mention_entity(
    client: WeaviateAsyncClient,
    document_mention_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> DocumentMentionResponse | None:
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None

    await upsert(
        client,
        DOCUMENT_MENTION_COLLECTION,
        document_mention_id,
        properties=dict(response.properties),
        references={
            "principal": require_reference_uuid(response.references, "principal"),
            "source": require_reference_uuid(response.references, "source"),
            "entity": entity_id,
        },
    )

    updated = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_object_by_id(
        document_mention_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if updated is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return document_mention_response(
        updated.properties,
        updated.references,
        updated.uuid,
    )


async def list_document_mentions(
    client: WeaviateAsyncClient,
    entity_id: uuid.UUID | None,
    source_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[DocumentMentionResponse]:
    filters: list[FilterReturn] = []
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    response = await client.collections.get(DOCUMENT_MENTION_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
        after=after_id,
    )
    items = sorted(
        [
            document_mention_response(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in response.objects
        ],
        key=lambda item: item.document_mention_id,
    )
    return items


# ---------------------------------------------------------------------------
# Faces
# ---------------------------------------------------------------------------


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
            "source": payload.source_id,
            "principal": payload.principal_id,
        },
        vector=single_named_vector_payload(DEFAULT_FACE_VECTOR, payload.embedding),
    )
    return FaceResponse(
        detection_id=detection_id,
        source_id=payload.source_id,
        bounding_box=payload.bounding_box,
        keypoints=payload.keypoints,
        principal_id=payload.principal_id,
        entity_id=payload.entity_id,
        confidence=payload.confidence,
    )


async def get_face(
    client: WeaviateAsyncClient,
    detection_id: uuid.UUID,
) -> FaceResponse | None:
    response = await client.collections.get(FACE_COLLECTION).query.fetch_object_by_id(
        detection_id,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return face_response(
        response.properties,
        response.references,
        response.uuid,
    )


async def patch_face_entity(
    client: WeaviateAsyncClient,
    detection_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> FaceResponse | None:
    response = await client.collections.get(FACE_COLLECTION).query.fetch_object_by_id(
        detection_id,
        include_vector=True,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None

    vector_payload: dict[str, list[float]] | None = None
    named_vectors: dict[str, list[float]] = {}
    for vector_name, vector_value in response.vector.items():
        if _is_flat_float_vector(vector_value):
            named_vectors[vector_name] = [float(item) for item in vector_value]
    if named_vectors:
        vector_payload = named_vectors

    await upsert(
        client,
        FACE_COLLECTION,
        detection_id,
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
        return None
    return face_response(
        updated.properties,
        updated.references,
        updated.uuid,
    )


async def list_faces(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[FaceResponse]:
    filters: list[FilterReturn] = []
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))
    response = await client.collections.get(FACE_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["principal", "entity", "source"]),
        after=after_id,
    )
    items = sorted(
        [
            face_response(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in response.objects
        ],
        key=lambda item: item.detection_id,
    )
    return items
