"""Pydantic schemas for source endpoints (spec §2.7 simplified source model)."""

import uuid

from pydantic import AliasChoices
from pydantic import AnyUrl
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import model_validator

from people_gator_api.schemas.enums import SourceKind


class PageSourceMetadata(BaseModel):
    """Metadata for a source representing a single page inside a document."""

    model_config = ConfigDict(extra="forbid")

    library: str
    document: uuid.UUID
    page: uuid.UUID
    kramerius_url: AnyUrl


class DocumentSourceMetadata(BaseModel):
    """Metadata for a source representing a full document."""

    model_config = ConfigDict(extra="forbid")

    library: str
    document: uuid.UUID
    kramerius_url: AnyUrl


class WikidataSourceMetadata(BaseModel):
    """Metadata for a source imported from Wikidata."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str = Field(validation_alias=AliasChoices("entity_id", "enitity_id"))
    wikidata_url: AnyUrl


class NlcrAuthoritySourceMetadata(BaseModel):
    """Metadata for a source imported from Czech National Authority DB (NLCR)."""

    model_config = ConfigDict(extra="forbid")

    nlcr_id: str


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
)


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
    }
    return isinstance(metadata, source_type_to_metadata_classes[source_type])


class SourceCreateRequest(BaseModel):
    """Request body for registering a source."""

    source_type: SourceKind
    uri: str
    metadata: SourceMetadata

    @model_validator(mode="after")
    def validate_metadata_for_source_type(self) -> "SourceCreateRequest":
        if not _metadata_allowed_for_source_type(self.source_type, self.metadata):
            raise ValueError(
                "metadata shape does not match source_type; expected strict metadata for the given source"
            )
        return self


class SourceResponse(BaseModel):
    """A single source record."""

    source_id: uuid.UUID
    source_type: SourceKind
    uri: str
    metadata: SourceMetadata | None


class SourceListResponse(BaseModel):
    """A paginated list of sources."""

    items: list[SourceResponse]
    total: int
    next_after_id: uuid.UUID | None = None
