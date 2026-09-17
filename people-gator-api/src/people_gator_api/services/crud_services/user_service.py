"""CRUD operations for users."""

import logging
import uuid

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateField

from people_gator_api.schemas.users import (
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.weaviate_service.db_schema import USER_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_user,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


@trace()
async def list_users(
    client: WeaviateAsyncClient,
    actor_user_id: uuid.UUID,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> UserListResponse:
    del actor_user_id
    logger.debug(
        "list_users called",
        extra={"is_active": is_active, "after_id": after_id, "limit": limit},
    )
    filters: list[FilterReturn] = []
    if is_active is not None:
        filters.append(Filter.by_property("is_active").equal(is_active))

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        USER_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        [parse_user(item.properties, item.references, item.uuid) for item in objects],
        key=lambda item: item.user_id,
    )
    return UserListResponse(
        items=items,
        total_count=total_count,
        after_id=items[-1].user_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def get_user(
    client: WeaviateAsyncClient,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
) -> UserResponse | None:
    del actor_user_id
    logger.debug("get_user called", extra={"user_id": target_user_id})
    response = await fetch_collection_object(client, USER_COLLECTION, target_user_id)
    if response is None:
        logger.info("user not found", extra={"user_id": target_user_id})
        return None
    return parse_user(response.properties, response.references, response.uuid)


async def _update_user(
    client: WeaviateAsyncClient,
    target_user_id: uuid.UUID,
    payload: UserPatchRequest,
) -> tuple[dict[str, WeaviateField], CrossReferences] | None:
    response = await fetch_collection_object(client, USER_COLLECTION, target_user_id)
    if response is None:
        logger.info("update_user skipped missing user", extra={"user_id": target_user_id})
        return None
    updates = payload.model_dump(exclude_unset=True)
    await client.collections.get(USER_COLLECTION).data.update(
        uuid=target_user_id,
        properties=updates,
    )
    properties = dict(response.properties)
    properties.update(updates)
    return properties, response.references


@trace()
async def get_or_create_user(
    client: WeaviateAsyncClient,
    *,
    external_subject: str,
    external_issuer: str,
) -> UserResponse:
    logger.info(
        "get_or_create_user called",
        extra={
            "external_subject": external_subject,
            "external_issuer": external_issuer,
        },
    )
    user_collection = client.collections.get(USER_COLLECTION)
    existing = await user_collection.query.fetch_objects(
        limit=1,
        filters=Filter.all_of(
            [
                Filter.by_property("external_subject").equal(external_subject),
                Filter.by_property("external_issuer").equal(external_issuer),
            ]
        ),
        return_references=empty_reference_queries([]),
    )
    if existing.objects:
        user = existing.objects[0]
        return parse_user(user.properties, user.references, user.uuid)

    user_id = new_uuid6()
    properties = {
        "display_name": external_subject,
        "is_active": True,
        "external_subject": external_subject,
        "external_issuer": external_issuer,
        "email": None,
    }
    await user_collection.data.insert(uuid=user_id, properties=properties)
    return UserResponse(
        user_id=user_id,
        display_name=external_subject,
        is_active=True,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=None,
    )


@trace()
async def update_user(
    client: WeaviateAsyncClient,
    actor_user_id: uuid.UUID,
    target_user_id: uuid.UUID,
    payload: UserPatchRequest,
) -> UserResponse | None:
    del actor_user_id
    updated = await _update_user(client, target_user_id, payload)
    if updated is None:
        return None
    properties, references = updated
    return parse_user(properties, references, target_user_id)
