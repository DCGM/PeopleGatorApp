"""DB model package — exports all SQLAlchemy mapped classes.

Import order matters: Base must be imported first so that the metadata registry
is populated before any migration tooling (Alembic) imports the models.
"""

from people_gator_api.db.models.base import Base
from people_gator_api.db.models.enums import (
    ClusterRole,
    DeltaType,
    EvidenceType,
    OperationType,
    ProcessingStatus,
    ProviderType,
    PrincipalType,
    RegistrySource,
    ResolverType,
    TaskRole,
    TaskStatus,
)
from people_gator_api.db.models.principal import (
    ModelAgent,
    Principal,
    ServiceAgent,
    User,
)
from people_gator_api.db.models.source_schema import SourceSchema
from people_gator_api.db.models.source import Source
from people_gator_api.db.models.evidence import (
    AuthorityEvidence,
    AuthorityIdentifierEvidence,
    DerivedEvidence,
    Evidence,
    FaceDetectionEvidence,
    GroundedDescriptionEvidence,
    GroundedNameEvidence,
    NamedEntityEvidence,
    TextRegionEvidence,
)
from people_gator_api.db.models.search_profile import SearchProfile, SearchProfileModality
from people_gator_api.db.models.cluster import Cluster
from people_gator_api.db.models.version import Version
from people_gator_api.db.models.operation import Operation
from people_gator_api.db.models.delta import Delta
from people_gator_api.db.models.membership import Membership
from people_gator_api.db.models.task import Task
from people_gator_api.db.models.source_processing import SourceProcessing

__all__ = [
    "Base",
    # enums
    "ClusterRole",
    "DeltaType",
    "EvidenceType",
    "OperationType",
    "ProcessingStatus",
    "ProviderType",
    "PrincipalType",
    "RegistrySource",
    "ResolverType",
    "TaskRole",
    "TaskStatus",
    # principals
    "Principal",
    "User",
    "ServiceAgent",
    "ModelAgent",
    # sources
    "SourceSchema",
    "Source",
    # evidence
    "Evidence",
    "DerivedEvidence",
    "FaceDetectionEvidence",
    "NamedEntityEvidence",
    "TextRegionEvidence",
    "AuthorityEvidence",
    "GroundedNameEvidence",
    "GroundedDescriptionEvidence",
    "AuthorityIdentifierEvidence",
    # search
    "SearchProfile",
    "SearchProfileModality",
    # cluster versioning
    "Cluster",
    "Version",
    "Operation",
    "Delta",
    "Membership",
    # tasks
    "Task",
    # processing
    "SourceProcessing",
]
