"""Pydantic schemas for source endpoints (spec §2.7 simplified source model)."""

import uuid
from people_gator_api.schemas.common import GenericListResponse

from pydantic import (
    AnyUrl,
    BaseModel,
    ConfigDict,
    model_validator,
)

from people_gator_api.schemas.enums import SourceKind


class PageSourceMetadata(BaseModel):
    """Metadata for a source representing a single page inside a document."""

    model_config = ConfigDict(extra="forbid")

    library: str
    document: uuid.UUID
    page: uuid.UUID
    kramerius_url: AnyUrl | None = None


class DocumentSourceMetadata(BaseModel):
    """Metadata for a source representing a full document."""

    model_config = ConfigDict(extra="forbid")
    library: str
    document: uuid.UUID


type SourceMetadata = PageSourceMetadata | DocumentSourceMetadata


class PageCreateRequest(BaseModel):
    """Typed page descriptor backed by a page Source record."""

    model_config = ConfigDict(extra="forbid")
    library: str
    document_id: uuid.UUID
    page_id: uuid.UUID


class DocumentCreateRequest(BaseModel):
    """Typed document descriptor backed by a document Source record."""

    model_config = ConfigDict(extra="forbid")
    library: str
    document_id: uuid.UUID


class ImageCreateRequest(BaseModel):
    """Typed image descriptor backed by an arbitrary URL Source record."""

    model_config = ConfigDict(extra="forbid")
    url: AnyUrl


class SourceDescriptorRequest(BaseModel):
    """Source selector used by annotation ingest endpoints."""

    model_config = ConfigDict(extra="forbid")
    page: PageCreateRequest | None = None
    document: DocumentCreateRequest | None = None
    image: ImageCreateRequest | None = None

    @model_validator(mode="after")
    def validate_source_descriptor(self) -> "SourceDescriptorRequest":
        descriptor_count = sum(
            (
                self.page is not None,
                self.document is not None,
                self.image is not None,
            )
        )
        if descriptor_count != 1:
            raise ValueError(
                "source descriptor requires exactly one of page, document, or image"
            )
        return self


class SourceResponse(BaseModel):
    """A linkable reference to a typed source."""

    model_config = ConfigDict(extra="forbid")

    source_id: uuid.UUID
    source_type: SourceKind
    uri: str


class SourceRecord(SourceResponse):
    """Internal persisted source data used by typed source services."""

    metadata: SourceMetadata | None


class SourceRecordListResponse(GenericListResponse[SourceRecord]):
    """Internal paginated source records for typed source services."""

    items: list[SourceRecord]


class SourceListResponse(GenericListResponse[SourceResponse]):
    """A paginated list of sources."""

    items: list[SourceResponse]


class PageResponse(BaseModel):
    """A page with its archive identity."""

    page_source_id: uuid.UUID
    library: str
    document_id: uuid.UUID
    page_id: uuid.UUID
    url: AnyUrl


class PageListResponse(GenericListResponse[PageResponse]):
    """A paginated list of pages."""

    items: list[PageResponse]


class DocumentResponse(BaseModel):
    """A document with its archive identity."""

    document_source_id: uuid.UUID
    library: str
    document_id: uuid.UUID
    url: AnyUrl


class DocumentListResponse(GenericListResponse[DocumentResponse]):
    """A paginated list of documents."""

    items: list[DocumentResponse]


class ImageResponse(BaseModel):
    """An image identified by an arbitrary URL."""

    image_id: uuid.UUID
    url: AnyUrl


class ImageListResponse(GenericListResponse[ImageResponse]):
    """A paginated list of images."""

    items: list[ImageResponse]
