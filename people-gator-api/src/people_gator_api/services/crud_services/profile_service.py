"""Service for search profile CRUD endpoints."""

import uuid
from collections.abc import Sequence

from weaviate import WeaviateAsyncClient
from weaviate.classes.query import Filter
from weaviate.classes.query import Sort

from people_gator_api.models.enums import AnnotationType
from people_gator_api.schemas.search_profiles import SearchProfileCloneRequest
from people_gator_api.schemas.search_profiles import SearchProfileCreateRequest
from people_gator_api.schemas.search_profiles import SearchProfileModalityOut
from people_gator_api.schemas.search_profiles import SearchProfilePatchRequest
from people_gator_api.schemas.search_profiles import SearchProfileResponse
from people_gator_api.services.vector_service.schema import SEARCH_PROFILE_COLLECTION
from people_gator_api.services.vector_service.schema import SEARCH_PROFILE_MODALITY_COLLECTION
from people_gator_api.services.weaviate_utils import MutableProperties
from people_gator_api.services.weaviate_utils import fetch_by_id
from people_gator_api.services.weaviate_utils import optional_float
from people_gator_api.services.weaviate_utils import optional_uuid
from people_gator_api.services.weaviate_utils import profile_modality_uuid
from people_gator_api.services.weaviate_utils import require_bool
from people_gator_api.services.weaviate_utils import require_float
from people_gator_api.services.weaviate_utils import require_str
from people_gator_api.services.weaviate_utils import require_uuid
from people_gator_api.services.weaviate_utils import upsert
from people_gator_api.utils.uuid_utils import new_uuid6


async def list_profiles(
    client: WeaviateAsyncClient,
    principal_id: uuid.UUID | None,
    include_system: bool,
    include_public: bool,
) -> list[SearchProfileResponse]:
    response = await client.collections.get(SEARCH_PROFILE_COLLECTION).query.fetch_objects(
        sort=Sort.by_property("profile_name", ascending=True),
        limit=500,
    )
    profiles = [
        await get_profile(client, require_uuid(item.properties, "profile_id"))
        for item in response.objects
    ]
    resolved = [profile for profile in profiles if profile is not None]
    filtered: list[SearchProfileResponse] = []
    for profile in resolved:
        if principal_id is not None and profile.owner_id == principal_id:
            filtered.append(profile)
            continue
        if include_system and profile.is_system:
            filtered.append(profile)
            continue
        if include_public and profile.is_public:
            filtered.append(profile)
    return filtered


async def get_profile(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
) -> SearchProfileResponse | None:
    obj = await fetch_by_id(client, SEARCH_PROFILE_COLLECTION, "profile_id", profile_id)
    if obj is None:
        return None
    modalities = await _list_profile_modalities(client, profile_id)
    properties = obj.properties
    return SearchProfileResponse(
        profile_id=require_uuid(properties, "profile_id"),
        profile_name=require_str(properties, "profile_name"),
        description=require_str(properties, "description")
        if properties.get("description") is not None
        else None,
        owner_id=optional_uuid(properties, "owner_id"),
        is_public=require_bool(properties, "is_public"),
        is_system=require_bool(properties, "is_system"),
        modalities=modalities,
    )


async def create_profile(
    client: WeaviateAsyncClient,
    owner_id: uuid.UUID,
    request: SearchProfileCreateRequest,
) -> SearchProfileResponse:
    profile_id = new_uuid6()
    await upsert(
        client,
        SEARCH_PROFILE_COLLECTION,
        profile_id,
        properties={
            "profile_id": profile_id,
            "profile_name": request.profile_name,
            "description": request.description,
            "owner_id": owner_id,
            "is_public": request.is_public,
            "is_system": False,
        },
        references={"owner": owner_id},
    )
    await _replace_profile_modalities(client, profile_id, request.modalities)
    profile = await get_profile(client, profile_id)
    assert profile is not None
    return profile


async def update_profile(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
    request: SearchProfilePatchRequest,
) -> SearchProfileResponse | None:
    obj = await fetch_by_id(client, SEARCH_PROFILE_COLLECTION, "profile_id", profile_id)
    if obj is None:
        return None
    properties: MutableProperties = dict(obj.properties)
    if request.profile_name is not None:
        properties["profile_name"] = request.profile_name
    if request.description is not None:
        properties["description"] = request.description
    if request.is_public is not None:
        properties["is_public"] = request.is_public

    owner_reference = optional_uuid(properties, "owner_id")
    await upsert(
        client,
        SEARCH_PROFILE_COLLECTION,
        profile_id,
        properties=properties,
        references={"owner": owner_reference} if owner_reference is not None else None,
    )
    if request.modalities is not None:
        await _replace_profile_modalities(client, profile_id, request.modalities)
    return await get_profile(client, profile_id)


async def delete_profile(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
) -> bool:
    profile = await get_profile(client, profile_id)
    if profile is None:
        return False
    modalities = await _list_profile_modality_ids(client, profile_id)
    for modality_id in modalities:
        await client.collections.get(SEARCH_PROFILE_MODALITY_COLLECTION).data.delete_by_id(
            modality_id
        )
    await client.collections.get(SEARCH_PROFILE_COLLECTION).data.delete_by_id(profile_id)
    return True


async def clone_profile(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
    owner_id: uuid.UUID,
    request: SearchProfileCloneRequest,
) -> SearchProfileResponse | None:
    source = await get_profile(client, profile_id)
    if source is None:
        return None
    cloned_profile_id = new_uuid6()
    await upsert(
        client,
        SEARCH_PROFILE_COLLECTION,
        cloned_profile_id,
        properties={
            "profile_id": cloned_profile_id,
            "profile_name": request.profile_name or f"{source.profile_name}-clone",
            "description": source.description,
            "owner_id": owner_id,
            "is_public": False,
            "is_system": False,
        },
        references={"owner": owner_id},
    )
    await _replace_profile_modalities(client, cloned_profile_id, source.modalities)
    cloned = await get_profile(client, cloned_profile_id)
    assert cloned is not None
    return cloned


async def _replace_profile_modalities(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
    modalities: Sequence[SearchProfileModalityOut] | Sequence[object],
) -> None:
    existing_ids = await _list_profile_modality_ids(client, profile_id)
    for modality_id in existing_ids:
        await client.collections.get(SEARCH_PROFILE_MODALITY_COLLECTION).data.delete_by_id(
            modality_id
        )

    for raw_modality in modalities:
        modality = (
            raw_modality
            if isinstance(raw_modality, SearchProfileModalityOut)
            else SearchProfileModalityOut.model_validate(raw_modality)
        )
        modality_id = profile_modality_uuid(profile_id, modality.annotation_type)
        references = {"profile": profile_id}
        if modality.model_id is not None:
            references["model_agent"] = modality.model_id
        await upsert(
            client,
            SEARCH_PROFILE_MODALITY_COLLECTION,
            modality_id,
            properties={
                "modality_id": modality_id,
                "profile_id": profile_id,
                "annotation_type": modality.annotation_type.value,
                "model_id": modality.model_id,
                "weight": modality.weight,
                "min_confidence": modality.min_confidence,
            },
            references=references,
        )


async def _list_profile_modalities(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
) -> list[SearchProfileModalityOut]:
    response = await client.collections.get(SEARCH_PROFILE_MODALITY_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("profile_id").equal(str(profile_id)),
        sort=Sort.by_property("annotation_type", ascending=True),
        limit=100,
    )
    return [
        SearchProfileModalityOut(
            annotation_type=AnnotationType(require_str(item.properties, "annotation_type")),
            weight=require_float(item.properties, "weight"),
            model_id=optional_uuid(item.properties, "model_id"),
            min_confidence=optional_float(item.properties, "min_confidence"),
        )
        for item in response.objects
    ]


async def _list_profile_modality_ids(
    client: WeaviateAsyncClient,
    profile_id: uuid.UUID,
) -> list[uuid.UUID]:
    response = await client.collections.get(SEARCH_PROFILE_MODALITY_COLLECTION).query.fetch_objects(
        filters=Filter.by_property("profile_id").equal(str(profile_id)),
        limit=100,
    )
    return [item.uuid for item in response.objects]
