"""Resolve entities and sources reached through assigned annotations."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Protocol, cast

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.internal import CrossReferences

from people_gator_api.schemas.enums import AssignmentType
from people_gator_api.services.weaviate_service.db_schema import (
    FACE_COLLECTION,
    TEXT_MENTION_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import empty_reference_queries

_ASSIGNMENT_PAGE_SIZE = 100
_COLLECTION_BY_ASSIGNMENT = {
    AssignmentType.face: FACE_COLLECTION,
    AssignmentType.text_mention: TEXT_MENTION_COLLECTION,
}


class _AssignedAnnotation(Protocol):
    uuid: uuid.UUID
    references: CrossReferences


async def assigned_reference_ids(
    client: WeaviateAsyncClient,
    assignment: AssignmentType,
    reference_name: str,
) -> set[uuid.UUID]:
    """Return unique entity or source IDs from assigned annotations."""
    collection = client.collections.get(_COLLECTION_BY_ASSIGNMENT[assignment])
    object_ids: set[uuid.UUID] = set()
    after_id: uuid.UUID | None = None
    while True:
        response = await collection.query.fetch_objects(
            filters=Filter.by_ref_count(link_on="entity").greater_than(0),
            limit=_ASSIGNMENT_PAGE_SIZE,
            after=after_id,
            return_properties=[],
            return_references=empty_reference_queries([reference_name]),
        )
        page = cast(Sequence[_AssignedAnnotation], response.objects)
        if not page:
            break
        for annotation in page:
            if reference_name in annotation.references:
                object_ids.update(
                    linked.uuid
                    for linked in annotation.references[reference_name].objects
                )
        if len(page) < _ASSIGNMENT_PAGE_SIZE:
            break
        next_after_id = page[-1].uuid
        if next_after_id == after_id:
            raise RuntimeError("Weaviate assignment pagination did not advance")
        after_id = next_after_id
    return object_ids


async def source_has_assignment(
    client: WeaviateAsyncClient,
    source_id: uuid.UUID,
    assignment: AssignmentType,
) -> bool:
    """Check whether a source contains at least one assigned annotation."""
    response = await client.collections.get(
        _COLLECTION_BY_ASSIGNMENT[assignment]
    ).query.fetch_objects(
        filters=Filter.all_of(
            [
                Filter.by_ref_count(link_on="entity").greater_than(0),
                Filter.by_ref("source").by_id().equal(source_id),
            ]
        ),
        limit=1,
        return_properties=[],
    )
    return bool(response.objects)
