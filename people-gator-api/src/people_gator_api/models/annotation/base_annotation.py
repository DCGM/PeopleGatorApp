"""ALTERNATIVE_NAME table — variant names from authorities (spec §2.5).

Stores name variants (birth name, pseudonym, transliteration, abbreviation)
from Wikidata, authority records, or manual curation.  Immutable once
created (spec §4.1).
"""

import logging
import uuid
import sqlalchemy as sa
from sqlalchemy import Enum as SAEnum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.ext.hybrid import hybrid_property

from people_gator_api.models.base import Base
from people_gator_api.models.enums import AnnotationType
from people_gator_api.utils.uuid_utils import new_uuid6

logger = logging.getLogger(__name__)


class BaseAnnotation(Base):
    """A variant name for a person attributed to an external source.

    ``name_type`` classifies the variant (birth name, pseudonym, etc.) and
    ``source_type``/``source_ref`` record provenance (spec §2.5).
    """
    __tablename__ = "base_annotation"
    annotation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=new_uuid6
    )
    type: Mapped[AnnotationType] = mapped_column(
        SAEnum(AnnotationType, name="annotation_type_enum"), nullable=False
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("source.source_id"),
        nullable=False,
    )
    principal_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("principal.principal_id"),
        nullable=False,
    )
    created_at: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )
    __mapped_args__ = {
        "polymorphic_identity": "base_annotation",
        "polymorphic_on": type,
    }

    @hybrid_property
    def is_alternative_name(self) -> bool: # pyright: ignore[reportRedeclaration]
        return self.type == AnnotationType.alternative_name
    
    @is_alternative_name.expression
    @classmethod
    def is_alternative_name(cls) -> sa.ColumnElement[bool]: 
        return cls.type == AnnotationType.alternative_name
    
    @hybrid_property
    def is_description(self) -> bool: # pyright: ignore[reportRedeclaration]
        return self.type == AnnotationType.description
    
    @is_description.expression
    @classmethod
    def is_description(cls) -> sa.ColumnElement[bool]:
        return cls.type == AnnotationType.description
    
    @hybrid_property
    def is_named_entity(self) -> bool: # pyright: ignore[reportRedeclaration]
        return self.type == AnnotationType.named_entity
    
    @is_named_entity.expression
    @classmethod
    def is_named_entity(cls) -> sa.ColumnElement[bool]:
        return cls.type == AnnotationType.named_entity
    
    @hybrid_property
    def is_detection(self) -> bool: # pyright: ignore[reportRedeclaration]
        return self.type == AnnotationType.detection
    
    @is_detection.expression
    @classmethod
    def is_detection(cls) -> sa.ColumnElement[bool]:
        return cls.type == AnnotationType.detection
