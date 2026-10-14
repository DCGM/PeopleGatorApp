from people_gator_api.schemas.common import GenericActor
# pyright: reportPrivateUsage=false

import uuid
from typing import cast as type_cast

import pytest
from pydantic import AnyUrl, ValidationError

from people_gator_api.persistence.contracts import EntityRepository, SourceRepository
from people_gator_api.schemas.common import GenericListResponse
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListFilter,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType, SourceKind
from people_gator_api.schemas.mentions import TextMentionResponse
from people_gator_api.schemas.missing import MISSING, is_missing
from people_gator_api.schemas.search import QueryBase
from people_gator_api.schemas.sources import (
    DocumentLookupRequest,
    GenericSourceLookupRequest,
    GenericSourceResponse,
    ImageListRequest,
    PageListFilter,
    PageListRequest,
    PageResponse,
    SourceListRequest,
    document_url,
    to_generic_list_request,
)
from people_gator_api.schemas.users import UserListFilter, UserPatchRequest


def test_typed_source_list_conversion_preserves_kind_and_count_request() -> None:
    page = to_generic_list_request(
        PageListRequest(limit=10, return_total_count=True)
    )
    image = to_generic_list_request(ImageListRequest(limit=5))
    generic = to_generic_list_request(SourceListRequest(limit=5))

    assert not is_missing(page.filter_)
    assert page.filter_.source_type == [SourceKind.page]
    assert page.return_total_count is True
    assert not is_missing(image.filter_)
    assert image.filter_.source_type == [SourceKind.image]
    assert generic.filter_ is MISSING


def test_page_annotation_filters_are_preserved_by_generic_conversion() -> None:
    generic = PageListFilter(
        has_mentions=True,
        has_faces=False,
        has_entities=True,
    ).to_generic()

    assert generic.has_mentions is True
    assert generic.has_faces is False
    assert generic.has_entities is True


def test_source_lookup_requires_one_complete_identity() -> None:
    document_id = uuid.uuid4()
    lookup = DocumentLookupRequest(
        library="mzk", document_id=document_id
    ).to_generic()
    assert lookup.source_type == SourceKind.document

    with pytest.raises(ValidationError):
        GenericSourceLookupRequest()
    with pytest.raises(ValidationError):
        GenericSourceLookupRequest(
            source_id=uuid.uuid4(), source_type=SourceKind.page
        )
    with pytest.raises(ValidationError):
        GenericSourceLookupRequest(source_type=SourceKind.document)


def test_filter_lists_must_not_be_empty() -> None:
    with pytest.raises(ValidationError):
        EntityListFilter(entity_id=[])
    with pytest.raises(ValidationError):
        UserListFilter(email=[])


def test_patch_models_are_optional_and_nullable_fields_can_be_cleared() -> None:
    assert UserPatchRequest().model_dump() == {}
    entity = EntityCreateRequest(
        entity_type=EntityType.person,
        name="Ada",
        description=None,
    )
    assert entity.description is None

    with pytest.raises(ValidationError):
        EntityCreateRequest(
            entity_type=EntityType.person,
            name="Ada",
            aliases=["A", "A"],
        )


def test_search_requires_unique_non_blank_query_items() -> None:
    assert QueryBase(text=["Ada"]).text == ["Ada"]
    with pytest.raises(ValidationError):
        QueryBase(text=[])
    with pytest.raises(ValidationError):
        QueryBase(text=[" "])
    face_id = uuid.uuid4()
    with pytest.raises(ValidationError):
        QueryBase(face_id=[face_id, face_id])


def test_list_response_enforces_page_shape() -> None:
    with pytest.raises(ValidationError):
        GenericListResponse[EntityResponse](items=[], limit=0, cursor="opaque")
    with pytest.raises(ValidationError):
        GenericListResponse[EntityResponse](items=[], limit=1, total_count=-1)


def test_text_mention_can_represent_entity_unlinking() -> None:
    response = TextMentionResponse(
        mention_id=uuid.uuid4(),
        name="Ada",
        context=None,
        entity_id=None,
        source_id=uuid.uuid4(),
    )
    assert response.entity_id is None


@pytest.mark.asyncio
async def test_empty_entity_delete_batch_is_a_noop() -> None:
    class Repository:
        async def delete_many(self, selector: object, *, context: object) -> object:
            raise AssertionError("delete_many must not be called")

    response = await EntityRepository.delete_batch(
        type_cast(EntityRepository, Repository()), [], context=GenericActor(user_id=uuid.uuid4())
    )
    assert response.deleted_count == 0


@pytest.mark.asyncio
async def test_typed_source_get_returns_none_for_wrong_kind() -> None:
    source_id = uuid.uuid4()

    class Repository:
        async def lookup(
            self, lookup: GenericSourceLookupRequest
        ) -> GenericSourceResponse:
            return GenericSourceResponse(
                source_id=source_id,
                source_type=SourceKind.document,
                library="mzk",
                document_id=(document_id := uuid.uuid4()),
                url=AnyUrl(document_url("mzk", document_id)),
            )

    result = await SourceRepository._lookup(
        type_cast(SourceRepository, Repository()),
        PageResponse,
        source_id=source_id,
    )
    assert result is None
