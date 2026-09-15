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
    kramerius_url: AnyUrl | None = None


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


class SourceCreateRequest(BaseModel):
    """Request body for registering a source."""

    source_type: SourceKind
    uri: str | None = None
    metadata: SourceMetadata | None = None

    @model_validator(mode="after")
    def validate_metadata_for_source_type(self) -> "SourceCreateRequest":
        if self.source_type == SourceKind.image:
            if self.metadata is not None:
                raise ValueError("image sources do not accept metadata")
            if self.uri is None:
                raise ValueError("image sources require uri")
            return self
        if self.uri is not None:
            raise ValueError("uri is derived from metadata for this source type")
        if self.metadata is None:
            raise ValueError("metadata is required for this source type")
        if self.source_type == SourceKind.page and not isinstance(
            self.metadata, PageSourceMetadata
        ):
            raise ValueError("page sources require page metadata")
        if self.source_type == SourceKind.document and not isinstance(
            self.metadata, DocumentSourceMetadata
        ):
            raise ValueError(
                "metadata shape does not match source_type; expected strict metadata for the given source"
            )
        return self


class SourceDescriptorRequest(BaseModel):
    """Source selector used by annotation ingest endpoints."""

    model_config = ConfigDict(extra="forbid")

    metadata: SourceMetadata | None = None
    page: PageCreateRequest | None = None
    document: DocumentCreateRequest | None = None
    image: ImageCreateRequest | None = None

    @model_validator(mode="after")
    def validate_source_descriptor(self) -> "SourceDescriptorRequest":
        descriptor_count = sum(
            (
                self.metadata is not None,
                self.page is not None,
                self.document is not None,
                self.image is not None,
            )
        )
        if descriptor_count != 1:
            raise ValueError(
                "source descriptor requires exactly one of metadata, page, document, or image"
            )
        return self


class SourceResponse(BaseModel):
    """A single source record."""

    source_id: uuid.UUID
    source_type: SourceKind
    uri: str
    metadata: SourceMetadata | None


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
