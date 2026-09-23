"""Pydantic schemas for source endpoints (spec §2.7 simplified source model)."""

from abc import abstractmethod
import uuid
from typing import Annotated, Self

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)
from people_gator_api.schemas.common import (
    GenericListRequest,
    GenericListResponse,
    ListFilterBase,
)
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.missing import MISSING, MissingType, is_missing


# ---------------------------------------------------------------------------
# URL templates and helper functions for Digitalni Knihovna library
# ---------------------------------------------------------------------------

"""Templates for constructing URLs within the Digitalni Knihovna library."""
DIGITALNIKNIHOVNA_PAGE_TEMPLATE = "https://www.digitalniknihovna.cz/{library}/view/uuid:{document_id}?page=uuid:{page_id}"


def page_url(library: str, document_id: uuid.UUID, page_id: uuid.UUID) -> str:
    """\
    Construct a URL for a specific page within a document in a library.
        Library: mzk
        Document ID: uuid:29834490-da53-49c5-9671-b686b01469d6
        Page ID: uuid:022b855c-b183-4cee-afe0-1acd6f972a6e
        Example url: https://www.digitalniknihovna.cz/mzk/view/uuid:29834490-da53-49c5-9671-b686b01469d6?page=uuid:022b855c-b183-4cee-afe0-1acd6f972a6e
    """

    return DIGITALNIKNIHOVNA_PAGE_TEMPLATE.format(
        library=library,
        document_id=document_id,
        page_id=page_id,
    )


"""Templates for constructing document URLs within the Digitalni Knihovna library."""
DIGITALNIKNIHOVNA_DOCUMENT_TEMPLATE = (
    "https://www.digitalniknihovna.cz/{library}/view/uuid:{document_id}"
)


def document_url(library: str, document_id: uuid.UUID) -> str:
    """\
    Construct a URL for a specific document within a library.
        Library: mzk
        Document ID: uuid:29834490-da53-49c5-9671-b686b01469d6
        Example url: https://www.digitalniknihovna.cz/mzk/view/uuid:29834490-da53-49c5-9671-b686b01469d6
    """

    return DIGITALNIKNIHOVNA_DOCUMENT_TEMPLATE.format(
        library=library,
        document_id=document_id,
    )


# ---------------------------------------------------------------------------
# Generic source create request
# ---------------------------------------------------------------------------


class GenericSourceCreateRequest(BaseModel):
    """\
    A generic source create request that can be used for any source type.
    CANNOT be exposed directly.
    ONLY FOR INTERNAL USE.
    """

    model_config = ConfigDict(extra="forbid")
    library: str | MissingType = Field(
        default=MISSING,
        description="The library identifier."
    )
    document_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The document identifier."
    )
    page_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The page identifier."
    )
    source_type: SourceKind = Field(
        description="The type of the source (e.g., page, document, image). Mandatory."
    )
    url: AnyUrl = Field(
        description="The URL of the source is mandatory and should be globally unique."
    )

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> Self:
        has_library = self.library is not MISSING
        has_document = self.document_id is not MISSING
        has_page = self.page_id is not MISSING

        if self.source_type == SourceKind.image:
            if has_library or has_document or has_page:
                raise ValueError("image sources must contain only source_type and url")
            return self

        if not has_library or not isinstance(self.library, str) or not self.library:
            raise ValueError("page and document sources require a non-empty library")
        if not has_document:
            raise ValueError("page and document sources require document_id")

        assert isinstance(self.library, str)
        assert isinstance(self.document_id, uuid.UUID)

        if self.source_type == SourceKind.document:
            if has_page:
                raise ValueError("document sources must not contain page_id")
            expected_url = document_url(self.library, self.document_id)
        else:
            if not has_page:
                raise ValueError("page sources require page_id")
            assert isinstance(self.page_id, uuid.UUID)
            expected_url = page_url(self.library, self.document_id, self.page_id)

        if str(self.url) != expected_url:
            raise ValueError(
                f"{self.source_type.value} url must be its canonical archive URL"
            )
        return self


# ---------------------------------------------------------------------------
# Page create request
# ---------------------------------------------------------------------------

class SourceCreateRequestBase(BaseModel):
    """Base class for all source create requests."""

    model_config = ConfigDict(extra="forbid")

    @abstractmethod
    def to_generic(self) -> GenericSourceCreateRequest:
        raise NotImplementedError()

class PageCreateRequest(SourceCreateRequestBase):
    """Typed page descriptor backed by a page Source record."""

    model_config = ConfigDict(extra="forbid")
    library: str = Field(min_length=1)
    document_id: uuid.UUID
    page_id: uuid.UUID

    def to_generic(self) -> GenericSourceCreateRequest:
        return GenericSourceCreateRequest(
            library=self.library,
            document_id=self.document_id,
            page_id=self.page_id,
            source_type=SourceKind.page,
            url=AnyUrl(page_url(self.library, self.document_id, self.page_id)),
        )


class DocumentCreateRequest(SourceCreateRequestBase):
    """Typed document descriptor backed by a document Source record."""

    model_config = ConfigDict(extra="forbid")
    library: str = Field(min_length=1)
    document_id: uuid.UUID

    def to_generic(self) -> GenericSourceCreateRequest:
        return GenericSourceCreateRequest(
            library=self.library,
            document_id=self.document_id,
            source_type=SourceKind.document,
            url=AnyUrl(document_url(self.library, self.document_id)),
        )


class ImageCreateRequest(SourceCreateRequestBase):
    """Typed image descriptor backed by an arbitrary URL Source record."""

    model_config = ConfigDict(extra="forbid")
    url: AnyUrl

    def to_generic(self) -> GenericSourceCreateRequest:
        return GenericSourceCreateRequest(
            source_type=SourceKind.image,
            url=self.url,
        )


# ---------------------------------------------------------------------------
# Batch create requests
# ---------------------------------------------------------------------------

# A bounded batch keeps the single preflight query and its exact OR filter at a
# predictable size while still making large imports practical.
MAX_MEDIA_BATCH_SIZE = 1_000
type PageBatchCreateRequest = Annotated[
    list[PageCreateRequest], Field(max_length=MAX_MEDIA_BATCH_SIZE)
]
type DocumentBatchCreateRequest = Annotated[
    list[DocumentCreateRequest], Field(max_length=MAX_MEDIA_BATCH_SIZE)
]
type ImageBatchCreateRequest = Annotated[
    list[ImageCreateRequest], Field(max_length=MAX_MEDIA_BATCH_SIZE)
]


# ---------------------------------------------------------------------------
# Special method for looking up single sources by their generic representation
# ---------------------------------------------------------------------------


class GenericSourceLookupRequest(BaseModel):
    """
    Request model for looking up a single source by its generic representation.
    Try to match to a specific source using its ID, URL, or associated document/page
    identifiers.

    Request has to have at least source_id or mandatory type+additional
    type-dependent fields (e.g., URL for images, library+document_id for documents,
    library+document_id+page_id for pages).
    """

    model_config = ConfigDict(extra="forbid")
    source_type: SourceKind | MissingType = Field(
        default=MISSING,
        description="The type of the source."
    )
    source_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The unique identifier of the source."
    )
    url: AnyUrl | MissingType = Field(
        default=MISSING,
        description="The URL of the source."
    )
    library: str | MissingType = Field(
        default=MISSING,
        description="The library identifier."
    )
    document_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The document identifier."
    )
    page_id: uuid.UUID | MissingType = Field(
        default=MISSING,
        description="The page identifier."
    )

    @model_validator(mode="after")
    def validate_lookup_key(self) -> Self:
        has_source_id = self.source_id is not MISSING
        has_source_type = self.source_type is not MISSING
        has_url = self.url is not MISSING
        has_library = self.library is not MISSING
        has_document = self.document_id is not MISSING
        has_page = self.page_id is not MISSING

        if has_library and (not isinstance(self.library, str) or not self.library):
            raise ValueError("library must be a non-empty string")

        if has_source_id:
            if has_source_type or has_url or has_library or has_document or has_page:
                raise ValueError("'source_id' must be the sole lookup key")
            return self

        if not has_source_type:
            raise ValueError(
                "provide either source_id or a complete type-specific identity"
            )

        if self.source_type == SourceKind.image:
            if not has_url or has_library or has_document or has_page:
                raise ValueError("image lookup requires only source_type and url")
        elif self.source_type == SourceKind.document:
            if has_url or not has_library or not has_document or has_page:
                raise ValueError(
                    "document lookup requires source_type, library, and document_id"
                )
        elif self.source_type == SourceKind.page:
            if has_url or not has_library or not has_document or not has_page:
                raise ValueError(
                    "page lookup requires source_type, library, document_id, and page_id"
                )
        return self


class PageLookupRequest(BaseModel):
    """Request model for looking up a single page by its generic representation."""

    library: str = Field(min_length=1)
    document_id: uuid.UUID
    page_id: uuid.UUID

    def to_generic(self) -> GenericSourceLookupRequest:
        return GenericSourceLookupRequest(
            source_type=SourceKind.page,
            library=self.library,
            document_id=self.document_id,
            page_id=self.page_id,
            source_id=MISSING,
            url=MISSING,
        )


class DocumentLookupRequest(BaseModel):
    """Request model for looking up a single document by its generic representation."""

    library: str = Field(min_length=1)
    document_id: uuid.UUID

    def to_generic(self) -> GenericSourceLookupRequest:
        return GenericSourceLookupRequest(
            source_type=SourceKind.document,
            library=self.library,
            document_id=self.document_id,
        )


class ImageLookupRequest(BaseModel):
    """Request model for looking up a single image by its generic representation."""

    url: AnyUrl

    def to_generic(self) -> GenericSourceLookupRequest:
        return GenericSourceLookupRequest(
            source_type=SourceKind.image,
            url=self.url,
        )



# ---------------------------------------------------------------------------
# Source response types
# ---------------------------------------------------------------------------


class SourceResponseBase(BaseModel):
    """A linkable reference to a typed source."""

    model_config = ConfigDict(extra="forbid")
    source_id: uuid.UUID
    source_type: SourceKind
    url: AnyUrl

    @classmethod
    def from_generic(cls, generic: GenericSourceResponse) -> Self:
        return cls(
            source_id=generic.source_id,
            source_type=generic.source_type,
            url=generic.url,
        )


class GenericSourceResponse(SourceResponseBase):
    """
    A generic source response that can be used for any source type.
    CANNOT be exposed directly.
    ONLY FOR INTERNAL USE.
    """

    model_config = ConfigDict(extra="forbid")
    library: str | None = Field(
        default=None,
        description="The library to which the source belongs.",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        description="The ID of the document to which the source belongs.",
    )
    page_id: uuid.UUID | None = Field(
        default=None,
        description="The ID of the page to which the source belongs.",
    )
    # All fields are optional to accommodate any source type.

    @model_validator(mode="after")
    def validate_type_specific_fields(self) -> Self:
        has_library = self.library is not None
        has_document = self.document_id is not None
        has_page = self.page_id is not None

        if self.source_type == SourceKind.image:
            if has_library or has_document or has_page:
                raise ValueError("image responses must not contain archive fields")
            return self

        if not has_library or not has_document:
            raise ValueError("archive source responses require library and document_id")
        assert self.library is not None
        assert self.document_id is not None

        if self.source_type == SourceKind.document:
            if has_page:
                raise ValueError("document responses must not contain page_id")
            expected_url = document_url(self.library, self.document_id)
        else:
            if not has_page:
                raise ValueError("page responses require page_id")
            assert self.page_id is not None
            expected_url = page_url(self.library, self.document_id, self.page_id)

        if str(self.url) != expected_url:
            raise ValueError(
                f"{self.source_type.value} response has a non-canonical URL"
            )
        return self


class PageResponse(SourceResponseBase):
    """A page with its archive identity."""

    library: str = Field(min_length=1)
    document_id: uuid.UUID
    page_id: uuid.UUID

    @classmethod
    def from_generic(cls, generic: GenericSourceResponse) -> PageResponse:
        if (
            generic.source_type != SourceKind.page
            or generic.library is None
            or generic.document_id is None
            or generic.page_id is None
        ):
            raise ValueError("Missing required fields in generic source response.")
        return cls(
            source_id=generic.source_id,
            source_type=generic.source_type,
            url=generic.url,
            library=generic.library,
            document_id=generic.document_id,
            page_id=generic.page_id,
        )


class DocumentResponse(SourceResponseBase):
    """A document with its archive identity."""

    library: str = Field(min_length=1)
    document_id: uuid.UUID

    @classmethod
    def from_generic(cls, generic: GenericSourceResponse) -> DocumentResponse:
        if (
            generic.source_type != SourceKind.document
            or generic.library is None
            or generic.document_id is None
        ):
            raise ValueError("Missing required fields in generic source response.")
        return cls(
            source_id=generic.source_id,
            source_type=generic.source_type,
            url=generic.url,
            library=generic.library,
            document_id=generic.document_id,
        )


class ImageResponse(SourceResponseBase):
    """An image identified by an arbitrary URL."""

    @classmethod
    def from_generic(cls, generic: GenericSourceResponse) -> ImageResponse:
        if generic.source_type != SourceKind.image:
            raise ValueError("Missing required fields in generic source response.")
        return cls(
            source_id=generic.source_id,
            source_type=generic.source_type,
            url=generic.url,
        )


GenericSourceListResponse = GenericListResponse[
    GenericSourceResponse
]  # DO NOT EXPOSE DIRECTLY
SourceListResponse = GenericListResponse[SourceResponseBase]
PageListResponse = GenericListResponse[PageResponse]
DocumentListResponse = GenericListResponse[DocumentResponse]
ImageListResponse = GenericListResponse[ImageResponse]

def to_source_list_response(generic_list: GenericSourceListResponse) -> SourceListResponse:
    return SourceListResponse(
        items=[SourceResponseBase.from_generic(item) for item in generic_list.items],
        total_count=generic_list.total_count,
        cursor=generic_list.cursor,
        limit=generic_list.limit,
    )

def to_page_list_response(generic_list: GenericSourceListResponse) -> PageListResponse:
    return PageListResponse(
        items=[PageResponse.from_generic(item) for item in generic_list.items],
        total_count=generic_list.total_count,
        cursor=generic_list.cursor,
        limit=generic_list.limit,
    )

def to_document_list_response(generic_list: GenericSourceListResponse) -> DocumentListResponse:
    return DocumentListResponse(
        items=[DocumentResponse.from_generic(item) for item in generic_list.items],
        total_count=generic_list.total_count,
        cursor=generic_list.cursor,
        limit=generic_list.limit,
    )

def to_image_list_response(generic_list: GenericSourceListResponse) -> ImageListResponse:
    return ImageListResponse(
        items=[ImageResponse.from_generic(item) for item in generic_list.items],
        total_count=generic_list.total_count,
        cursor=generic_list.cursor,
        limit=generic_list.limit,
    )

# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------


class GenericSourceListFilter(ListFilterBase):
    """Filter for listing generic sources."""

    source_type: list[SourceKind] | MissingType = Field(
        default=MISSING,
        description="Filter by source type."
    )
    url: list[AnyUrl] | MissingType = Field(
        default=MISSING,
        description="Filter by URL."
    )
    library: list[str] | MissingType = Field(
        default=MISSING,
        description="Filter by library."
    )
    document_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by document ID."
    )
    page_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by page ID."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by source ID."
    )
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by entity ID that occur on source through text mention or face link."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked detection ID."
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked mention ID."
    )


class SourceListFilter(ListFilterBase):
    """Filter for listing all sources."""

    source_type: list[SourceKind] | MissingType = Field(
        default=MISSING,
        description="Filter by source type."
    )
    url: list[AnyUrl] | MissingType = Field(
        default=MISSING,
        description="Filter by URL."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by source ID."
    )
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by entity ID that occur on source through text mention or face link."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked detection ID."
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked mention ID."
    )

    def to_generic(self) -> GenericSourceListFilter:
        return GenericSourceListFilter(
            source_type=self.source_type,
            url=self.url,
            source_id=self.source_id,
            entity_id=self.entity_id,
            detection_id=self.detection_id,
            mention_id=self.mention_id,
            library=MISSING,
            page_id=MISSING,
            document_id=MISSING,
        )


class PageListFilter(ListFilterBase):
    """Filter for listing pages."""

    url: list[AnyUrl] | MissingType = Field(
        default=MISSING,
        description="Filter by URL."
    )
    library: list[str] | MissingType = Field(
        default=MISSING,
        description="Filter by library."
    )
    document_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by document ID."
    )
    page_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by page ID."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by source ID."
    )
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by entity ID that occur on source through text mention or face link."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked detection ID."
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked mention ID."
    )

    def to_generic(self) -> GenericSourceListFilter:
        return GenericSourceListFilter(
            source_type=[SourceKind.page],
            url=self.url,
            library=self.library,
            document_id=self.document_id,
            page_id=self.page_id,
            source_id=self.source_id,
            entity_id=self.entity_id,
            detection_id=self.detection_id,
            mention_id=self.mention_id,
        )


class DocumentListFilter(ListFilterBase):
    """Filter for listing documents."""

    url: list[AnyUrl] | MissingType = Field(
        default=MISSING,
        description="Filter by URL."
    )
    library: list[str] | MissingType = Field(
        default=MISSING,
        description="Filter by library."
    )
    document_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by document ID."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by source ID."
    )
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by entity ID that occur on source through text mention or face link."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked detection ID."
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked mention ID."
    )

    def to_generic(self) -> GenericSourceListFilter:
        return GenericSourceListFilter(
            source_type=[SourceKind.document],
            url=self.url,
            library=self.library,
            document_id=self.document_id,
            source_id=self.source_id,
            entity_id=self.entity_id,
            detection_id=self.detection_id,
            mention_id=self.mention_id,
        )


class ImageListFilter(ListFilterBase):
    """Filter for listing images."""

    url: list[AnyUrl] | MissingType = Field(
        default=MISSING,
        description="Filter by URL."
    )
    source_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by source ID."
    )
    entity_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by entity ID that occur on source through text mention or face link."
    )
    detection_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked detection ID."
    )
    mention_id: list[uuid.UUID] | MissingType = Field(
        default=MISSING,
        description="Filter by linked mention ID."
    )

    def to_generic(self) -> GenericSourceListFilter:
        return GenericSourceListFilter(
            source_type=[SourceKind.image],
            url=self.url,
            source_id=self.source_id,
            entity_id=self.entity_id,
            detection_id=self.detection_id,
            mention_id=self.mention_id,
        )


def to_generic_list_filter(
    filter: PageListFilter
    | DocumentListFilter
    | ImageListFilter
    | SourceListFilter
    | MissingType,
    source_type: SourceKind | None = None,
) -> GenericSourceListFilter | MissingType:
    """Flatten a typed filter while preserving its source-kind constraint."""

    if source_type is None:
        if isinstance(filter, PageListFilter):
            source_type = SourceKind.page
        elif isinstance(filter, DocumentListFilter):
            source_type = SourceKind.document
        elif isinstance(filter, ImageListFilter):
            source_type = SourceKind.image

    if is_missing(filter):
        if source_type is None:
            return MISSING
        return GenericSourceListFilter(source_type=[source_type])

    generic_filter = filter.to_generic()
    if source_type is not None:
        generic_filter.source_type = [source_type]
    return generic_filter


# ---------------------------------------------------------------------------
# List requests
# ---------------------------------------------------------------------------

class SourceListRequest(GenericListRequest):
    filter: SourceListFilter | MissingType = Field(
        default=MISSING, description="Filter for listing sources."
    )


class PageListRequest(GenericListRequest):
    filter: PageListFilter | MissingType = Field(
        default=MISSING,
        description="Filter for listing pages."
    )


class DocumentListRequest(GenericListRequest):
    filter: DocumentListFilter | MissingType = Field(
        default=MISSING,
        description="Filter for listing documents."
    )


class ImageListRequest(GenericListRequest):
    filter: ImageListFilter | MissingType = Field(
        default=MISSING,
        description="Filter for listing images."
    )


class GenericSourceListRequest(GenericListRequest):
    filter: GenericSourceListFilter | MissingType = Field(
        default=MISSING,
        description="Filter for listing generic sources."
    )


def to_generic_list_request(
    request: PageListRequest
    | DocumentListRequest
    | ImageListRequest
    | SourceListRequest,
) -> GenericSourceListRequest:
    if isinstance(request, PageListRequest):
        source_type = SourceKind.page
    elif isinstance(request, DocumentListRequest):
        source_type = SourceKind.document
    elif isinstance(request, ImageListRequest):
        source_type = SourceKind.image
    else:
        source_type = None

    return GenericSourceListRequest(
        filter=to_generic_list_filter(request.filter, source_type),
        limit=request.limit,
        return_total_count=request.return_total_count,
        cursor=request.cursor,
    )


__all__ = [
    "page_url",
    "document_url",

    "GenericSourceCreateRequest",
    "PageCreateRequest",
    "DocumentCreateRequest",
    "ImageCreateRequest",

    "PageBatchCreateRequest",
    "DocumentBatchCreateRequest",
    "ImageBatchCreateRequest",

    "GenericSourceLookupRequest",
    "PageLookupRequest",
    "DocumentLookupRequest",
    "ImageLookupRequest",

    "SourceResponseBase",
    "GenericSourceResponse",
    "PageResponse",
    "DocumentResponse",
    "ImageResponse",

    "SourceListResponse",
    "GenericSourceListResponse",
    "PageListResponse",
    "DocumentListResponse",
    "ImageListResponse",
    "to_source_list_response",
    "to_page_list_response",
    "to_document_list_response",
    "to_image_list_response",

    "GenericSourceListFilter",
    "DocumentListFilter",
    "PageListFilter",
    "ImageListFilter",
    "SourceListFilter",
    "to_generic_list_filter",

    "GenericSourceListRequest",
    "PageListRequest",
    "DocumentListRequest",
    "ImageListRequest",
    "SourceListRequest",
    "to_generic_list_request",
]
