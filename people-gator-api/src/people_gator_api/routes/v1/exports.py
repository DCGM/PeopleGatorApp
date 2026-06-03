from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.schemas.exports import ClusterStateExportRequest, ExportResponse, IaaExportRequest
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.export_service import (
    export_cluster_state,
    export_inter_annotator_agreement,
)

router = APIRouter(tags=["export"])


@router.post("/export/cluster-state", response_model=ExportResponse)
async def export_cluster_state_route(
    payload: ClusterStateExportRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> ExportResponse:
    data = await export_cluster_state(session, payload.cluster_ids, payload.include_history)
    return ExportResponse(export_type="cluster_state", payload=data)


@router.post("/export/inter-annotator-agreement", response_model=ExportResponse)
async def export_iaa_route(
    payload: IaaExportRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:review")),
    session: AsyncSession = Depends(get_session),
) -> ExportResponse:
    data = await export_inter_annotator_agreement(session, payload.cluster_id, payload.pinned_version_id)
    return ExportResponse(export_type="inter_annotator_agreement", payload=data)
