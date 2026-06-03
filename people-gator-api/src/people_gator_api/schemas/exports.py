import uuid

from pydantic import BaseModel


class ClusterStateExportRequest(BaseModel):
    cluster_ids: list[uuid.UUID] = []
    format: str
    include_history: bool = False


class IaaExportRequest(BaseModel):
    cluster_id: uuid.UUID
    pinned_version_id: uuid.UUID


class ExportResponse(BaseModel):
    export_type: str
    payload: dict[str, object]
