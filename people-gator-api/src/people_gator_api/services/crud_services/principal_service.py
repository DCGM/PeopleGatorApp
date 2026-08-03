import uuid

from weaviate import (
    WeaviateAsyncClient,
)
from weaviate.collections.classes.filters import (
    FilterReturn,
)
from weaviate.classes.query import (
    Filter,
)

from people_gator_api.schemas.enums import (
    PrincipalType,
)
from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    PrincipalResponse,
)
from people_gator_api.services.vector_service.schema import (
    PRINCIPAL_COLLECTION,
)
from people_gator_api.services.weaviate_utils import (
    MutableProperties,
    StoredUser,
    combine_filters,
    fetch_by_id,
    fetch_single,
    principal_response,
    query_objects,
    require_bool,
    require_uuid,
    upsert,
)
from people_gator_api.utils.uuid_utils import (
    new_uuid6,
)


async def list_principals(
    client: WeaviateAsyncClient,
    principal_type: PrincipalType | None,
    is_active: bool | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[PrincipalResponse]:
    scan_limit = max(limit * 10, 1000)
    filters: list[FilterReturn] = []
    if principal_type is not None:
        filters.append(Filter.by_property("principal_type").equal(principal_type.value))
    if is_active is not None:
        filters.append(Filter.by_property("is_active").equal(is_active))

    response = await client.collections.get(PRINCIPAL_COLLECTION).query.fetch_objects(
        filters=combine_filters(filters),
        limit=scan_limit,
    )
    objects = query_objects(response)
    items = sorted(
        [principal_response(item.properties) for item in objects],
        key=lambda item: item.principal_id,
    )
    if after_id is not None:
        items = [item for item in items if item.principal_id > after_id]
    return items[:limit]


async def get_principal(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID,
) -> PrincipalResponse | None:
    obj = await fetch_by_id(client, PRINCIPAL_COLLECTION, "principal_id", principal_id)
    if obj is None:
        return None
    return principal_response(obj.properties)


async def get_or_create_user(
    client: WeaviateAsyncClient,
    *,
    external_subject: str,
    external_issuer: str,
    display_name: str,
    email: str | None,
) -> StoredUser:
    existing = await fetch_single(
        client,
        PRINCIPAL_COLLECTION,
        Filter.all_of(
            [
                Filter.by_property("principal_type").equal(PrincipalType.user.value),
                Filter.by_property("external_subject").equal(external_subject),
                Filter.by_property("external_issuer").equal(external_issuer),
            ]
        ),
    )

    principal_id = (
        require_uuid(existing.properties, "principal_id")
        if existing is not None
        else new_uuid6()
    )
    is_active_value = (
        require_bool(existing.properties, "is_active")
        if existing is not None
        else True
    )
    properties: MutableProperties = {
        "principal_id": principal_id,
        "principal_type": PrincipalType.user.value,
        "display_name": display_name,
        "is_active": is_active_value,
        "external_subject": external_subject,
        "external_issuer": external_issuer,
        "email": email,
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
        display_name=display_name,
        is_active=is_active_value,
        external_subject=external_subject,
        external_issuer=external_issuer,
        email=email,
    )


async def create_model_agent(
    client: WeaviateAsyncClient,
    payload: ModelAgentCreateRequest,
) -> PrincipalResponse:
    existing = await fetch_single(
        client,
        PRINCIPAL_COLLECTION,
        Filter.all_of(
            [
                Filter.by_property("principal_type").equal(PrincipalType.model_agent.value),
                Filter.by_property("annotation_type").equal(payload.annotation_type.value),
                Filter.by_property("role").equal(payload.role),
                Filter.by_property("model_slug").equal(payload.model_slug),
            ]
        ),
    )

    principal_id = (
        require_uuid(existing.properties, "principal_id")
        if existing is not None
        else new_uuid6()
    )
    await upsert(
        client,
        PRINCIPAL_COLLECTION,
        principal_id,
        properties={
            "principal_id": principal_id,
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
    obj = await fetch_by_id(client, PRINCIPAL_COLLECTION, "principal_id", principal_id)
    if obj is None:
        return None
    properties: MutableProperties = dict(obj.properties)
    if display_name is not None:
        properties["display_name"] = display_name
    if is_active is not None:
        properties["is_active"] = is_active
    await upsert(client, PRINCIPAL_COLLECTION, principal_id, properties=properties)
    return principal_response(dict(properties))
