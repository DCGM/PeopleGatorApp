"""DB model package — exports all SQLAlchemy mapped classes.

Import order matters: Base must be imported first so that the metadata registry
is populated before any migration tooling (Alembic) imports the models.
"""

from people_gator_api.models.base import Base
from people_gator_api.models.enums import (
    AnnotationType,
    ConsensusMethod,
    Decision,
    EntityType,
    NameType,
    PrincipalType,
    RecordSource,
    RegistrySource,
    SourceKind,
)
from people_gator_api.models.principal import (
    ModelAgent,
    Principal,
    ServiceAgent,
    User,
)
from people_gator_api.models.source import Source
from people_gator_api.models.identity import Identity
from people_gator_api.models.annotation import (
    NamedEntity,
    Detection,
    Description,
    AlternativeName
)
from people_gator_api.models.link import LinkConsensus, LinkDecision
from people_gator_api.models.search_profile import SearchProfile, SearchProfileModality

__all__ = [
    "Base",
    # enums
    "AnnotationType",
    "ConsensusMethod",
    "Decision",
    "EntityType",
    "NameType",
    "PrincipalType",
    "RecordSource",
    "RegistrySource",
    "SourceKind",
    # principals
    "Principal",
    "User",
    "ServiceAgent",
    "ModelAgent",
    # sources
    "Source",
    # identity + annotations
    "Identity",
    "NamedEntity",
    "Detection",
    "Description",
    "AlternativeName",
    # consensus
    "LinkDecision",
    "LinkConsensus",
    # search
    "SearchProfile",
    "SearchProfileModality",
]
