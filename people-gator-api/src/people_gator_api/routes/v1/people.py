"""Typed person endpoints (#123): the Person projection of the entity repository.

Like ``/documents`` and ``/pages`` over ``/sources``, these routes read and write
only people and expose the person fields, filters and sorts. ``/entities``
keeps the shared entity fields.
"""

import uuid

from fastapi import APIRouter, Response, status

from people_gator_api.persistence.contracts import (
    EntityTypeConflictError,
    InvalidPersonFieldsError,
)
from people_gator_api.routes.v1.query_dependencies import (
    DEFAULT_SORT,
    ListRequestDependency,
    PersonListFilterDependency,
    PersonListSortDependency,
)
from people_gator_api.schemas.entities import (
    PersonBatchCreateRequest,
    PersonBatchPatchRequest,
    PersonCreateRequest,
    PersonListRequest,
    PersonListResponse,
    PersonMergeBatchRequest,
    PersonMergeBatchResponse,
    PersonMergeFromRequest,
    PersonMergeResponse,
    PersonPatchRequest,
    PersonResponse,
)
from people_gator_api.services.auth_service import (
    AdminActorDependency,
    AnnotatorActorDependency,
    BrowseActorDependency,
)
from people_gator_api.services.database_service import DatabaseDependency
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter(tags=["people"])

NOT_FOUND = "Person not found"


@router.get("/people", response_model=PersonListResponse)
async def list_people_route(
    database: DatabaseDependency,
    user: BrowseActorDependency,
    filter: PersonListFilterDependency,
    list_request: ListRequestDependency,
    sort: PersonListSortDependency = DEFAULT_SORT,
) -> PersonListResponse:
    del user
    try:
        return await database.entities.list_people(
            PersonListRequest(
                filter_=filter,
                limit=list_request.limit,
                return_total_count=list_request.return_total_count,
                cursor=list_request.cursor,
                sort=sort.sort,
                sort_direction=sort.sort_direction,
            )
        )
    except NotImplementedError as exc:
        raise_api_error(501, "unsupported_operation", str(exc))
    except ValueError as exc:
        raise_api_error(422, "invalid_query", str(exc))


@router.get("/people/{entity_id}", response_model=PersonResponse)
async def get_person_route(
    entity_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseActorDependency,
) -> PersonResponse:
    del user
    person = await database.entities.get_person(entity_id)
    if person is None:
        raise_api_error(404, "not_found", NOT_FOUND)
    return person


@router.post("/people", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
async def create_person_route(
    payload: PersonCreateRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> PersonResponse:
    try:
        return await database.entities.create_person(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.post(
    "/people:batch",
    response_model=list[PersonResponse],
    status_code=status.HTTP_201_CREATED,
)
async def create_person_batch_route(
    payload: PersonBatchCreateRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> list[PersonResponse]:
    try:
        return await database.entities.create_person_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))


@router.patch(
    "/people:batch",
    response_model=list[PersonResponse | None],
    description="Patch people; omitted fields are preserved and null clears. Missing IDs and non-person entities return null.",
)
async def patch_person_batch_route(
    payload: PersonBatchPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> list[PersonResponse | None]:
    try:
        return await database.entities.patch_person_batch(payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))


@router.patch(
    "/people/{entity_id}",
    response_model=PersonResponse,
    description="Patch a person; omitted fields are preserved and null clears. A death date before the birth date, including the stored one, returns 422.",
)
async def patch_person_route(
    entity_id: uuid.UUID,
    payload: PersonPatchRequest,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> PersonResponse:
    try:
        person = await database.entities.patch_person(entity_id, payload, user)
    except ValueError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    if person is None:
        raise_api_error(404, "not_found", NOT_FOUND)
    return person


@router.put(
    "/people/{entity_id}",
    response_model=PersonResponse,
    summary="Create or replace a person",
    description="Create the person with this UUID if it does not exist (201), otherwise replace its fields (200). Omitted optional fields, including names and life dates, are cleared on replace. Linked faces, text mentions and the portrait selection are kept. A UUID of another entity type returns 409.",
    responses={
        status.HTTP_200_OK: {"description": "The existing person was replaced."},
        status.HTTP_201_CREATED: {
            "model": PersonResponse,
            "description": "The person was created with this UUID.",
        },
        status.HTTP_409_CONFLICT: {"description": "The UUID belongs to another entity type."},
    },
)
async def put_person_route(
    entity_id: uuid.UUID,
    payload: PersonCreateRequest,
    response: Response,
    database: DatabaseDependency,
    user: AnnotatorActorDependency,
) -> PersonResponse:
    try:
        result = await database.entities.put_person(entity_id, payload, user)
    except EntityTypeConflictError as exc:
        raise_api_error(409, "entity_type_conflict", str(exc))
    except ValueError as exc:
        raise_api_error(422, "invalid_reference", str(exc))
    if result.created:
        response.status_code = status.HTTP_201_CREATED
    return result.person


@router.delete("/people/{entity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person_route(
    entity_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> None:
    if not await database.entities.delete_person(entity_id, context=user):
        raise_api_error(404, "not_found", NOT_FOUND)


@router.post(
    "/people/{target_entity_id}:merge",
    response_model=PersonMergeResponse,
    summary="Merge one person into this target",
    description="Reassign the source person's faces and text mentions to the target in the URL, add its aliases without duplicates, then delete the source. Optional description, name and life-date fields update the target; null clears them and omission preserves the target's values.",
)
async def merge_person_route(
    target_entity_id: uuid.UUID,
    payload: PersonMergeFromRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> PersonMergeResponse:
    try:
        result = await database.entities.merge_person(target_entity_id, payload, context=user)
    except InvalidPersonFieldsError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    except ValueError as exc:
        raise_api_error(409, "invalid_merge", str(exc))
    if result is None:
        raise_api_error(404, "not_found", "Source or target person not found")
    return result


@router.post(
    "/people/{target_entity_id}:merge-batch",
    response_model=PersonMergeBatchResponse,
    summary="Merge multiple people into this target",
    description="Atomically reassign every source person's faces and text mentions to the target in the URL, add their aliases without duplicates, then delete all sources. Optional description, name and life-date fields update the target; null clears them and omission preserves the target's values.",
)
async def merge_person_batch_route(
    target_entity_id: uuid.UUID,
    payload: PersonMergeBatchRequest,
    database: DatabaseDependency,
    user: AdminActorDependency,
) -> PersonMergeBatchResponse:
    try:
        result = await database.entities.merge_people(target_entity_id, payload, context=user)
    except InvalidPersonFieldsError as exc:
        raise_api_error(422, "invalid_patch", str(exc))
    except ValueError as exc:
        raise_api_error(409, "invalid_merge", str(exc))
    if result is None:
        raise_api_error(404, "not_found", "Target or source person not found")
    return result
