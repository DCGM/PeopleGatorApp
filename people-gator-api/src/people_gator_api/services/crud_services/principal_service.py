import logging
import uuid
from dataclasses import dataclass

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn
from weaviate.classes.query import Filter

from people_gator_api.schemas.enums import PrincipalType
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    PrincipalResponse,
    PrincipalListResponse,
)
from people_gator_api.services.weaviate_service.db_schema import PRINCIPAL_COLLECTION
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    principal_response,
    require_bool,
    upsert,
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
    principal_type: PrincipalType | None,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> PrincipalListResponse:
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
async def get_principal(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
) -> PrincipalResponse | None:
    logger.debug("get_principal called", extra={"principal_id": principal_id})
    response = await client.collections.get(
        PRINCIPAL_COLLECTION
    ).query.fetch_object_by_id(
        principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info("principal not found", extra={"principal_id": principal_id})
        return None
    logger.debug("principal found", extra={"principal_id": principal_id})
    return principal_response(response.properties, response.references, response.uuid)


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

    principal_id = (
        getattr(existing.objects[0], "uuid") if existing.objects else new_uuid6()
    )
    await upsert(
        client,
        PRINCIPAL_COLLECTION,
        principal_id,
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
    resolved = await get_principal(client, principal_id)
    assert resolved is not None
    logger.info("create_model_agent completed", extra={"principal_id": principal_id})
    return resolved


@trace()
async def update_principal(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    display_name: str | None,
    is_active: bool | None,
) -> PrincipalResponse | None:
    logger.info("update_principal called", extra={"principal_id": principal_id})
    response = await client.collections.get(
        PRINCIPAL_COLLECTION
    ).query.fetch_object_by_id(
        principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        logger.info(
            "update_principal skipped missing principal",
            extra={"principal_id": principal_id},
        )
        return None
    properties = dict(response.properties)
    if display_name is not None:
        properties["display_name"] = display_name
    if is_active is not None:
        properties["is_active"] = is_active
    await upsert(client, PRINCIPAL_COLLECTION, principal_id, properties=properties)
    logger.debug("update_principal persisted", extra={"principal_id": principal_id})
    return await get_principal(client, principal_id)
