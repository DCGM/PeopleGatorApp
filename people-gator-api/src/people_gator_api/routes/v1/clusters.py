import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.db.models.enums import ClusterRole
from people_gator_api.schemas.clusters import (
    BranchOperationBody,
    ClusterCreateRequest,
    ClusterPatchRequest,
    ClusterSummary,
    DeltaResponse,
    DeltaWriteRequest,
    MembershipResponse,
    MergeOperationBody,
    OperationResult,
    SplitOperationBody,
    StageOperationBody,
    VersionDetailResponse,
    VersionSummary,
)
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.cluster_service import (
    create_manual_cluster,
    execute_operation,
    get_cluster_summary,
    get_membership,
    get_versions,
    list_clusters,
    list_pending_deltas,
    list_version_operations,
    patch_cluster_head,
    write_delta,
)
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["clusters"])


@router.get("/clusters", response_model=list[ClusterSummary])
async def list_clusters_route(
    cluster_role: list[ClusterRole] = Query(default_factory=list),
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[ClusterSummary]:
    return await list_clusters(session, cluster_role, after_id, limit)


@router.get("/clusters/{cluster_id}", response_model=ClusterSummary)
async def get_cluster_route(
    cluster_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> ClusterSummary:
    cluster = await get_cluster_summary(session, cluster_id)
    if cluster is None:
        raise_api_error(404, "not_found", "Cluster not found")
    return cluster


@router.options("/clusters/{cluster_id}")
async def options_cluster_route(
    cluster_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
) -> dict[str, object]:
    return {
        "cluster_id": str(cluster_id),
        "allowed_methods": ["GET", "HEAD", "OPTIONS", "PATCH", "POST"],
        "allowed_operations": [],
    }


@router.post("/clusters", response_model=ClusterSummary, status_code=status.HTTP_201_CREATED)
async def create_cluster_route(
    payload: ClusterCreateRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> ClusterSummary:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    return await create_manual_cluster(session, auth.principal.principal_id, payload.cluster_role)


@router.patch("/clusters/{cluster_id}", response_model=ClusterSummary)
async def patch_cluster_route(
    cluster_id: uuid.UUID,
    payload: ClusterPatchRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:review")),
    session: AsyncSession = Depends(get_session),
) -> ClusterSummary:
    updated = await patch_cluster_head(
        session,
        cluster_id,
        payload.head_version_id,
        payload.expected_head_version_id,
    )
    if updated is None:
        raise_api_error(409, "concurrent_head_advance", "Could not advance cluster head")
    return updated


@router.get("/clusters/{cluster_id}/membership", response_model=MembershipResponse)
async def get_membership_route(
    cluster_id: uuid.UUID,
    version_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> MembershipResponse:
    response = await get_membership(session, cluster_id, version_id)
    return response


@router.get("/clusters/{cluster_id}/versions", response_model=list[VersionSummary])
async def list_versions_route(
    cluster_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> list[VersionSummary]:
    return await get_versions(session, cluster_id)


@router.get("/clusters/{cluster_id}/versions/{version_id}", response_model=VersionDetailResponse)
async def get_version_route(
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
    session: AsyncSession = Depends(get_session),
) -> VersionDetailResponse:
    versions = await get_versions(session, cluster_id)
    version = next((row for row in versions if row.version_id == version_id), None)
    if version is None:
        raise_api_error(404, "not_found", "Version not found")
    incoming, outgoing = await list_version_operations(session, cluster_id, version_id)
    return VersionDetailResponse(version=version, incoming_operations=incoming, outgoing_operations=outgoing)


@router.get("/clusters/{cluster_id}/versions/{version_id}/pending", response_model=list[uuid.UUID])
async def pending_route(
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> list[uuid.UUID]:
    rows = await list_pending_deltas(session, cluster_id, version_id)
    return [row.delta_id for row in rows]


@router.post("/clusters/{cluster_id}/versions/{version_id}/deltas", response_model=DeltaResponse, status_code=status.HTTP_201_CREATED)
async def write_delta_route(
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
    payload: DeltaWriteRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> DeltaResponse:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")
    delta = await write_delta(session, cluster_id, version_id, auth.principal.principal_id, payload)
    return DeltaResponse(delta_id=delta.delta_id)


@router.get("/clusters/{cluster_id}/versions/{version_id}/deltas", response_model=list[DeltaResponse])
async def list_deltas_route(
    cluster_id: uuid.UUID,
    version_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> list[DeltaResponse]:
    rows = await list_pending_deltas(session, cluster_id, version_id)
    return [DeltaResponse(delta_id=row.delta_id) for row in rows]


@router.post("/clusters/{cluster_id}/operations", response_model=OperationResult)
async def operation_route(
    cluster_id: uuid.UUID,
    payload: StageOperationBody | BranchOperationBody | MergeOperationBody | SplitOperationBody,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> OperationResult:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")

    if isinstance(payload, MergeOperationBody) or isinstance(payload, SplitOperationBody):
        _ = Depends(require_scopes("people-gator:review"))

    try:
        return await execute_operation(session, cluster_id, auth.principal.principal_id, payload)
    except LookupError:
        raise_api_error(404, "not_found", "Cluster not found")
    except ValueError:
        raise_api_error(422, "invalid_operation", "Operation payload is invalid")


@router.get("/clusters/{cluster_id}/similar")
async def similar_clusters_route(
    cluster_id: uuid.UUID,
    limit: int = 10,
    _auth: AuthContext = Depends(require_scopes("people-gator:browse", allow_anonymous=True)),
) -> dict[str, object]:
    return {
        "total": 0,
        "limit": limit,
        "next_after_id": None,
        "results": [],
        "query": {"reference_cluster_id": str(cluster_id)},
    }
