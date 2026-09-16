import logging
import uuid

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn
from weaviate.collections.classes.internal import CrossReferences
from weaviate.collections.classes.types import WeaviateField
from weaviate.classes.query import Filter

from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    ModelAgentListResponse,
    ModelAgentPatchRequest,
    ModelAgentResponse,
    PrincipalCreateRequest,
    PrincipalPatchRequest,
    PrincipalResponse,
    PrincipalListResponse,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.services.weaviate_service.db_schema import PRINCIPAL_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_model_agent,
    parse_principal,
    parse_user,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


class PrincipalAlreadyExistsError(ValueError):
    """Raised when a principal with the requested unique identity exists."""


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

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        PRINCIPAL_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_principal(item.properties, item.references, item.uuid)
            for item in objects
        ],
        key=lambda item: item.principal_id,
    )
    return PrincipalListResponse(
        items=items,
        total_count=total_count,
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

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        PRINCIPAL_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_model_agent(item.properties, item.references, item.uuid)
            for item in objects
        ],
        key=lambda item: item.principal_id,
    )
    return ModelAgentListResponse(
        items=items,
        total_count=total_count,
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

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        PRINCIPAL_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries([]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_user(item.properties, item.references, item.uuid)
            for item in objects
        ],
        key=lambda item: item.principal_id,
    )
    return UserListResponse(
        items=items,
        total_count=total_count,
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
    response = await fetch_collection_object(
        client, PRINCIPAL_COLLECTION, target_principal_id
    )
    if response is None:
        logger.info("principal not found", extra={"principal_id": target_principal_id})
        return None
    logger.debug("principal found", extra={"principal_id": target_principal_id})
    return parse_principal(response.properties, response.references, response.uuid)


@trace()
async def get_user(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
) -> UserResponse | None:
    del actor_principal_id
    logger.debug("get_user called", extra={"principal_id": target_principal_id})
    response = await fetch_collection_object(
        client, PRINCIPAL_COLLECTION, target_principal_id
    )
    if response is None:
        logger.info("user not found", extra={"principal_id": target_principal_id})
        return None
    if response.properties.get("principal_type") != PrincipalType.user.value:
        logger.info(
            "principal is not a user",
            extra={"principal_id": target_principal_id},
        )
        return None
    logger.debug("user found", extra={"principal_id": target_principal_id})
    return parse_user(response.properties, response.references, response.uuid)


@trace()
async def get_model_agent(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
) -> ModelAgentResponse | None:
    del actor_principal_id
    logger.debug("get_model_agent called", extra={"principal_id": target_principal_id})
    response = await fetch_collection_object(
        client, PRINCIPAL_COLLECTION, target_principal_id
    )
    if response is None:
        logger.info(
            "model agent not found", extra={"principal_id": target_principal_id}
        )
        return None
    if response.properties.get("principal_type") != PrincipalType.model_agent.value:
        logger.info(
            "principal is not a model agent",
            extra={"principal_id": target_principal_id},
        )
        return None
    logger.debug("model agent found", extra={"principal_id": target_principal_id})
    return parse_model_agent(response.properties, response.references, response.uuid)


async def _create_principal(
    client: WeaviateAsyncClient,
    *,
    principal_type: PrincipalType,
    payload: PrincipalCreateRequest,
    additional_properties: dict[str, str | bool | None] | None = None,
    uniqueness_filters: list[FilterReturn] | None = None,
) -> uuid.UUID:
    logger.info(
        "create_principal called",
        extra={
            "principal_type": principal_type.value,
            "display_name": payload.display_name,
            "is_active": payload.is_active,
        },
    )
    filters: list[FilterReturn] = [
        Filter.by_property("principal_type").equal(principal_type.value)
    ]
    if uniqueness_filters is not None:
        filters.extend(uniqueness_filters)

    principal_collection = client.collections.get(PRINCIPAL_COLLECTION)
    existing = await principal_collection.query.fetch_objects(
        limit=1,
        filters=combine_filters(filters),
    )
    if existing.objects:
        existing_principal_id = existing.objects[0].uuid
        logger.info(
            "create_principal rejected duplicate",
            extra={
                "principal_type": principal_type.value,
                "principal_id": existing_principal_id,
            },
        )
        raise PrincipalAlreadyExistsError(
            f"{principal_type.value} principal already exists"
        )

    created_principal_id = new_uuid6()
    properties = {
        "principal_type": principal_type.value,
        "display_name": payload.display_name,
        "is_active": payload.is_active,
        "external_subject": None,
        "external_issuer": None,
        "email": None,
        "annotation_type": None,
        "role": None,
        "model_slug": None,
        "model_version": None,
        "registry_source": None,
        "registry_uri": None,
    }
    if additional_properties is not None:
        properties.update(additional_properties)
    await principal_collection.data.insert(
        uuid=created_principal_id,
        properties=properties,
    )
    return created_principal_id


async def _update_principal(
    client: WeaviateAsyncClient,
    target_principal_id: uuid.UUID,
    payload: PrincipalPatchRequest,
    *,
    additional_properties: dict[str, str | bool | None] | None = None,
) -> tuple[dict[str, WeaviateField], CrossReferences] | None:
    logger.info("update_principal called", extra={"principal_id": target_principal_id})
    response = await fetch_collection_object(
        client, PRINCIPAL_COLLECTION, target_principal_id
    )
    if response is None:
        logger.info(
            "update_principal skipped missing principal",
            extra={"principal_id": target_principal_id},
        )
        return None
    updates = payload.model_dump(exclude_unset=True)
    if additional_properties is not None:
        updates.update(additional_properties)
    await client.collections.get(PRINCIPAL_COLLECTION).data.update(
        uuid=target_principal_id,
        properties=updates,
    )
    properties = dict(response.properties)
    properties.update(updates)
    logger.debug(
        "update_principal persisted", extra={"principal_id": target_principal_id}
    )
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
    user_collection = client.collections.get(PRINCIPAL_COLLECTION)
    existing = await user_collection.query.fetch_objects(
        limit=1,
        filters=Filter.all_of(
            [
                Filter.by_property("principal_type").equal(PrincipalType.user.value),
                Filter.by_property("external_subject").equal(external_subject),
                Filter.by_property("external_issuer").equal(external_issuer),
            ]
        ),
        return_references=empty_reference_queries([]),
    )

    if existing.objects:
        user = existing.objects[0]
        return parse_user(user.properties, user.references, user.uuid)

    principal_id = new_uuid6()
    properties = {
        "principal_type": PrincipalType.user.value,
        "display_name": external_subject,
        "is_active": True,
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
    await user_collection.data.insert(
        uuid=principal_id,
        properties=properties,
    )
    return UserResponse(
        principal_id=principal_id,
        principal_type=PrincipalType.user,
        display_name=external_subject,
        is_active=True,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=None,
    )


@trace()
async def create_model_agent(
    client: WeaviateAsyncClient,
    payload: ModelAgentCreateRequest,
    actor_principal_id: uuid.UUID,
) -> ModelAgentResponse:
    del actor_principal_id
    logger.info(
        "create_model_agent called",
        extra={
            "model_slug": payload.model_slug,
            "model_version": payload.model_version,
        },
    )
    created_principal_id = await _create_principal(
        client,
        principal_type=PrincipalType.model_agent,
        payload=payload,
        additional_properties={
            "model_slug": payload.model_slug,
            "model_version": payload.model_version,
        },
        uniqueness_filters=[
            Filter.by_property("model_slug").equal(payload.model_slug),
            Filter.by_property("model_version").equal(payload.model_version),
        ],
    )
    logger.info(
        "create_model_agent completed",
        extra={"principal_id": created_principal_id},
    )
    return ModelAgentResponse(
        principal_id=created_principal_id,
        principal_type=PrincipalType.model_agent,
        display_name=payload.display_name,
        is_active=payload.is_active,
        model_slug=payload.model_slug,
        model_version=payload.model_version,
    )


@trace()
async def update_user(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
    payload: UserPatchRequest,
) -> UserResponse | None:
    del actor_principal_id
    updated = await _update_principal(
        client,
        target_principal_id,
        payload,
    )
    if updated is None:
        return None
    properties, references = updated
    return parse_user(properties, references, target_principal_id)


@trace()
async def update_model_agent(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
    payload: ModelAgentPatchRequest,
) -> ModelAgentResponse | None:
    del actor_principal_id
    updated = await _update_principal(
        client,
        target_principal_id,
        payload,
    )
    if updated is None:
        return None
    properties, references = updated
    return parse_model_agent(properties, references, target_principal_id)


@trace()
async def delete_model_agent(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
) -> bool:
    logger.info(
        "delete_model_agent called", extra={"principal_id": target_principal_id}
    )
    model_agent = await get_model_agent(client, actor_principal_id, target_principal_id)
    if model_agent is None:
        return False
    deleted = await client.collections.get(PRINCIPAL_COLLECTION).data.delete_by_id(
        target_principal_id
    )
    logger.info(
        "delete_model_agent completed",
        extra={"principal_id": target_principal_id},
    )
    return deleted


@trace()
async def update_principal(
    client: WeaviateAsyncClient,
    actor_principal_id: uuid.UUID,
    target_principal_id: uuid.UUID,
    display_name: str | None,
    is_active: bool | None,
) -> PrincipalResponse | None:
    del actor_principal_id
    updated = await _update_principal(
        client,
        target_principal_id,
        PrincipalPatchRequest(display_name=display_name, is_active=is_active),
    )
    if updated is None:
        return None
    properties, references = updated
    return parse_principal(properties, references, target_principal_id)
