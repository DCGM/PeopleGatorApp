import logging
import uuid
from dataclasses import dataclass

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn
from weaviate.classes.query import Filter

from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    ModelAgentListResponse,
    PrincipalResponse,
    PrincipalListResponse,
    UserListResponse,
    UserResponse,
)
from people_gator_api.services.weaviate_service.db_schema import PRINCIPAL_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    model_agent_response,
    principal_response,
    require_bool,
    upsert,
    user_response,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class StoredUser:
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool
    external_subject: str
    external_issuer: str
    email: str | None


@trace()
async def list_principals(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    principal_type: PrincipalType | None,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> PrincipalListResponse:
    del actor_principal_id
    logger.debug(
        "list_principals called",
        extra={
            "principal_type": principal_type.value
            if principal_type is not None
            else None,
            "is_active": is_active,
            "after_id": after_id,
            "limit": limit,
        },
    )
    filters: list[FilterReturn] = []
    if principal_type is not None:
        filters.append(Filter.by_property("principal_type").equal(principal_type.value))
    if is_active is not None:
        filters.append(Filter.by_property("is_active").equal(is_active))

    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after=after_id,
    )
    items = sorted(
        [
            principal_response(item.properties, item.references, item.uuid)
            for item in response.objects
        ],
        key=lambda item: item.principal_id,
    )
    return PrincipalListResponse(
        items=items,
        total_count=len(items),
        after_id=items[-1].principal_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def list_model_agents(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> ModelAgentListResponse:
    del actor_principal_id
    logger.debug(
        "list_model_agents called",
        extra={
            "is_active": is_active,
            "after_id": after_id,
            "limit": limit,
        },
    )
    filters: list[FilterReturn] = [
        Filter.by_property("principal_type").equal(PrincipalType.model_agent.value)
    ]
    if is_active is not None:
        filters.append(Filter.by_property("is_active").equal(is_active))

    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after=after_id,
    )
    items = sorted(
        [
            model_agent_response(item.properties, item.references, item.uuid)
            for item in response.objects
        ],
        key=lambda item: item.principal_id,
    )
    return ModelAgentListResponse(
        items=items,
        total_count=len(items),
        after_id=items[-1].principal_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def list_users(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> UserListResponse:
    del actor_principal_id
    logger.debug(
        "list_users called",
        extra={
            "is_active": is_active,
            "after_id": after_id,
            "limit": limit,
        },
    )
    filters: list[FilterReturn] = [
        Filter.by_property("principal_type").equal(PrincipalType.user.value)
    ]
    if is_active is not None:
        filters.append(Filter.by_property("is_active").equal(is_active))

    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after=after_id,
    )
    items = sorted(
        [
            user_response(item.properties, item.references, item.uuid)
            for item in response.objects
        ],
        key=lambda item: item.principal_id,
    )
    return UserListResponse(
        items=items,
        total_count=len(items),
        after_id=items[-1].principal_id if len(items) == limit and items else None,
        limit=limit,
    )


@trace()
async def get_principal(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
) -> PrincipalResponse | None:
    del actor_principal_id
    logger.debug("get_principal called", extra={"principal_id": target_principal_id})
    response = await client.collections.get(
        PRINCIPAL_COLLECTION
    ).query.fetch_object_by_id(
        target_principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("principal not found", extra={"principal_id": target_principal_id})
        return None
    logger.debug("principal found", extra={"principal_id": target_principal_id})
    return principal_response(response.properties, response.references, response.uuid)


@trace()
async def get_user(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
) -> UserResponse | None:
    del actor_principal_id
    logger.debug("get_user called", extra={"principal_id": target_principal_id})
    response = await client.collections.get(
        PRINCIPAL_COLLECTION
    ).query.fetch_object_by_id(
        target_principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("user not found", extra={"principal_id": target_principal_id})
        return None
    if response.properties.get("principal_type") != PrincipalType.user.value:
        logger.info(
            "principal is not a user",
            extra={"principal_id": target_principal_id},
        )
        return None
    logger.debug("user found", extra={"principal_id": target_principal_id})
    return user_response(response.properties, response.references, response.uuid)


@trace()
async def get_or_create_user(
    client: WeaviateAsyncClient,
    *,
    external_subject: str,
    external_issuer: str,
) -> StoredUser:
    logger.info(
        "get_or_create_user called",
        extra={
            "external_subject": external_subject,
            "external_issuer": external_issuer,
        },
    )
    existing = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        limit=1,
        filters=Filter.all_of(
            [
                Filter.by_property("principal_type").equal(PrincipalType.user.value),
                Filter.by_property("external_subject").equal(external_subject),
                Filter.by_property("external_issuer").equal(external_issuer),
            ]
        ),
    )

    if existing.objects:
        existing_item = existing.objects[0]
        principal_id = existing_item.uuid
        existing_properties = existing_item.properties
        is_active_value = require_bool(existing_properties, "is_active")
        logger.info(
            "existing user principal found", extra={"principal_id": principal_id}
        )
    else:
        principal_id = new_uuid6()
        is_active_value = True
        logger.info("creating new user principal", extra={"principal_id": principal_id})

    properties = {
        "principal_type": PrincipalType.user.value,
        "display_name": external_subject,
        "is_active": is_active_value,
        "external_subject": external_subject,
        "external_issuer": external_issuer,
        "email": None,
        "annotation_type": None,
        "role": None,
        "model_slug": None,
        "model_version": None,
        "registry_source": None,
        "registry_uri": None,
    }
    await upsert(
        client,
        PRINCIPAL_COLLECTION,
        principal_id,
        properties=properties,
    )
    return StoredUser(
        principal_id=principal_id,
        principal_type=PrincipalType.user,
        display_name=external_subject,
        is_active=is_active_value,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=None,
    )


@trace()
async def create_model_agent(
    client: WeaviateAsyncClient,
    payload: ModelAgentCreateRequest,
    actor_principal_id: uuid.UUID,
) -> PrincipalResponse:
    logger.info(
        "create_model_agent called",
        extra={
            "model_slug": payload.model_slug,
            "model_version": payload.model_version,
        },
    )
    existing = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        limit=1,
        filters=Filter.all_of(
            [
                Filter.by_property("principal_type").equal(
                    PrincipalType.model_agent.value
                ),
                Filter.by_property("model_slug").equal(payload.model_slug),
                Filter.by_property("model_version").equal(payload.model_version),
            ]
        ),
    )

    created_principal_id = (
        getattr(existing.objects[0], "uuid") if existing.objects else new_uuid6()
    )
    await upsert(
        client,
        PRINCIPAL_COLLECTION,
        created_principal_id,
        properties={
            "principal_type": PrincipalType.model_agent.value,
            "display_name": payload.display_name,
            "is_active": payload.is_active,
            "external_subject": None,
            "external_issuer": None,
            "email": None,
            "model_slug": payload.model_slug,
            "model_version": payload.model_version,
            "annotation_type": None,
            "role": None,
            "registry_source": None,
            "registry_uri": None,
        },
    )
    resolved = await get_principal(
        client,
        actor_principal_id,
        created_principal_id,
    )
    assert resolved is not None
    logger.info(
        "create_model_agent completed",
        extra={"principal_id": created_principal_id},
    )
    return resolved


@trace()
async def update_principal(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
    display_name: str | None,
    is_active: bool | None,
) -> PrincipalResponse | None:
    logger.info("update_principal called", extra={"principal_id": target_principal_id})
    response = await client.collections.get(
        PRINCIPAL_COLLECTION
    ).query.fetch_object_by_id(
        target_principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "update_principal skipped missing principal",
            extra={"principal_id": target_principal_id},
        )
        return None
    if response.uuid != target_principal_id:
        logger.error(
            "refusing principal update due to UUID mismatch",
            extra={
                "expected_principal_id": target_principal_id,
                "loaded_principal_id": response.uuid,
            },
        )
        raise RuntimeError("Principal ID is immutable and cannot be changed")
    properties = dict(response.properties)
    if display_name is not None:
        properties["display_name"] = display_name
    if is_active is not None:
        properties["is_active"] = is_active
    await upsert(
        client, PRINCIPAL_COLLECTION, target_principal_id, properties=properties
    )
    logger.debug(
        "update_principal persisted", extra={"principal_id": target_principal_id}
    )
    return await get_principal(client, actor_principal_id, target_principal_id)
