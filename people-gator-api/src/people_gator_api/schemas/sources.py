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


class WikidataSourceMetadata(BaseModel):
    """Metadata for a source imported from Wikidata."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    wikidata_url: AnyUrl


class NlcrAuthoritySourceMetadata(BaseModel):
    """Metadata for a source imported from Czech National Authority DB (NLCR)."""

    model_config = ConfigDict(extra="forbid")

    nlcr_id: str


class ObalkyKnihSourceMetadata(BaseModel):
    """Metadata for a source imported from ObalkyKnih.cz."""

    model_config = ConfigDict(extra="forbid")

    obalkyknih_id: str
    obalkyknih_url: AnyUrl


class WikimediaImageSourceMetadata(BaseModel):
    """Metadata for a source imported from Wikimedia image repositories."""

    model_config = ConfigDict(extra="forbid")

    wikimedia_url: AnyUrl


type SourceMetadata = (
    PageSourceMetadata
    | DocumentSourceMetadata
    | WikidataSourceMetadata
    | NlcrAuthoritySourceMetadata
    | WikimediaImageSourceMetadata
    | ObalkyKnihSourceMetadata
)


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


def _metadata_allowed_for_source_type(
    source_type: SourceKind,
    metadata: SourceMetadata,
) -> bool:
    source_type_to_metadata_classes: dict[SourceKind, tuple[type[BaseModel], ...]] = {
        SourceKind.page: (PageSourceMetadata,),
        SourceKind.document: (DocumentSourceMetadata,),
        SourceKind.wikidata: (WikidataSourceMetadata,),
        SourceKind.wikimedia: (WikimediaImageSourceMetadata,),
        SourceKind.nlcr: (NlcrAuthoritySourceMetadata,),
        SourceKind.obalkyknih: (ObalkyKnihSourceMetadata,),
    }
    return isinstance(metadata, source_type_to_metadata_classes[source_type])


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
        if not _metadata_allowed_for_source_type(self.source_type, self.metadata):
            raise ValueError(
                "metadata shape does not match source_type; expected strict metadata for the given source"
            )
        return self


class SourceDescriptorRequest(BaseModel):
    """Source selector used by annotation ingest endpoints."""

    model_config = ConfigDict(extra="forbid")

    uri: str | None = None
    metadata: SourceMetadata | None = None
    page: PageCreateRequest | None = None
    document: DocumentCreateRequest | None = None
    image: ImageCreateRequest | None = None

    @model_validator(mode="after")
    def validate_source_descriptor(self) -> "SourceDescriptorRequest":
        legacy_descriptor = self.uri is not None or self.metadata is not None
        descriptor_count = sum(
            (
                legacy_descriptor,
                self.page is not None,
                self.document is not None,
                self.image is not None,
            )
        )
        if descriptor_count != 1:
            raise ValueError(
                "source descriptor requires exactly one of uri/metadata, page, document, or image"
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
