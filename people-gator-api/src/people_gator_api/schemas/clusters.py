import uuid

from pydantic import BaseModel

from people_gator_api.db.models.enums import ClusterRole, OperationType


class ClusterSummary(BaseModel):
    cluster_id: uuid.UUID
    head_version_id: uuid.UUID | None
    cluster_role: ClusterRole | None


class ClusterCreateRequest(BaseModel):
    cluster_role: ClusterRole


class ClusterPatchRequest(BaseModel):
    head_version_id: uuid.UUID
    expected_head_version_id: uuid.UUID


class MembershipItem(BaseModel):
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    weight: float
    as_of_version_id: uuid.UUID


class MembershipResponse(BaseModel):
    cluster_id: uuid.UUID
    version_id: uuid.UUID | None
    members: list[MembershipItem]


class VersionSummary(BaseModel):
    version_id: uuid.UUID
    cluster_id: uuid.UUID
    cluster_role: ClusterRole
    actor_id: uuid.UUID
    search_profile_id: uuid.UUID | None


class VersionDetailResponse(BaseModel):
    version: VersionSummary
    incoming_operations: list[OperationType]
    outgoing_operations: list[OperationType]


class DeltaWriteRequest(BaseModel):
    evidence_id: uuid.UUID
    evidence_version_id: uuid.UUID
    delta_type: str
    weight: float | None = None


class DeltaResponse(BaseModel):
    delta_id: uuid.UUID


class StageOperationBody(BaseModel):
    operation_type: str
    source_version_id: uuid.UUID
    cluster_role: ClusterRole


class BranchOperationBody(BaseModel):
    operation_type: str
    source_version_id: uuid.UUID
    cluster_role: ClusterRole


class SourceVersionRef(BaseModel):
    cluster_id: uuid.UUID
    version_id: uuid.UUID


class MergeOperationBody(BaseModel):
    operation_type: str
    source_versions: list[SourceVersionRef]
    cluster_role: ClusterRole


class SplitTargetBody(BaseModel):
    cluster_role: ClusterRole
    evidence_ids: list[uuid.UUID] = []


class SplitOperationBody(BaseModel):
    operation_type: str
    source_version_id: uuid.UUID
    split_targets: list[SplitTargetBody]


class OperationResult(BaseModel):
    operation_id: uuid.UUID | None
    version_id: uuid.UUID | None
    split_targets: list[ClusterSummary] = []
