import uuid
from collections.abc import (
    Mapping,
)
from dataclasses import (
    dataclass,
)

from weaviate import (
    WeaviateAsyncClient,
)
from weaviate.collections.classes.filters import (
    FilterReturn,
)
from weaviate.classes.query import (
    Filter,
)
from weaviate.collections.classes.types import (
    WeaviateField,
)

from people_gator_api.schemas.enums import (
    PrincipalType,
)
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    PrincipalResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    PRINCIPAL_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    MutableProperties,
    combine_filters,
    empty_reference_queries,
    principal_response,
    require_bool,
    require_str,
    optional_str,
    upsert,
)
from people_gator_api.utils.uuid_utils import (
    new_uuid6,
)


@dataclass(slots=True, frozen=True)
class StoredUser:
    principal_id: uuid.UUID
    principal_type: PrincipalType
    display_name: str
    is_active: bool
    external_subject: str
    external_issuer: str
    email: str | None


async def list_principals(
    client: WeaviateAsyncClient,
    principal_type: PrincipalType | None,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[PrincipalResponse]:
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
        [principal_response(item.properties, item.references, item.uuid) for item in response.objects],
        key=lambda item: item.principal_id,
    )
    return items


async def get_principal(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
) -> PrincipalResponse | None:
    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_object_by_id(
        principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    return principal_response(response.properties, response.references, response.uuid)


async def get_or_create_user(
    client: WeaviateAsyncClient,
    *,
    external_subject: str,
    external_issuer: str,
    display_name: str,
    email: str | None,
) -> StoredUser:
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
        principal_id = getattr(existing_item, "uuid")
        existing_properties = existing_item.properties
        is_active_value = require_bool(existing_properties, "is_active")
        resolved_display_name = require_str(existing_properties, "display_name")
        resolved_email = optional_str(existing_properties, "email")
    else:
        principal_id = new_uuid6()
        is_active_value = True
        resolved_display_name = display_name
        resolved_email = email

    properties: MutableProperties = {
        "principal_type": PrincipalType.user.value,
        "display_name": resolved_display_name,
        "is_active": is_active_value,
        "external_subject": external_subject,
        "external_issuer": external_issuer,
        "email": resolved_email,
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
        display_name=resolved_display_name,
        is_active=is_active_value,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=resolved_email,
    )


async def create_model_agent(
    client: WeaviateAsyncClient,
    payload: ModelAgentCreateRequest,
) -> PrincipalResponse:
    existing = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        limit=1,
        filters=Filter.all_of(
            [
                Filter.by_property("principal_type").equal(PrincipalType.model_agent.value),
                Filter.by_property("annotation_type").equal(payload.annotation_type.value),
                Filter.by_property("role").equal(payload.role),
                Filter.by_property("model_slug").equal(payload.model_slug),
            ]
        ),
    )

    principal_id = getattr(existing.objects[0], "uuid") if existing.objects else new_uuid6()
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
            "annotation_type": payload.annotation_type.value,
            "role": payload.role,
            "model_slug": payload.model_slug,
            "model_version": payload.model_version,
            "registry_source": payload.registry_source.value,
            "registry_uri": payload.registry_uri,
        },
    )
    resolved = await get_principal(client, principal_id)
    assert resolved is not None
    return resolved


async def update_principal(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
    display_name: str | None,
    is_active: bool | None,
) -> PrincipalResponse | None:
    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_object_by_id(
        principal_id,
        return_references=empty_reference_queries([]),
    )
    if response is None:  # type: ignore[reportUnnecessaryComparison] - Weaviate returns None at runtime for missing UUIDs despite narrowed overload return typing.
        return None
    properties = dict(response.properties)
    if display_name is not None:
        properties["display_name"] = display_name
    if is_active is not None:
        properties["is_active"] = is_active
    await upsert(client, PRINCIPAL_COLLECTION, principal_id, properties=properties)
    return await get_principal(client, principal_id)
