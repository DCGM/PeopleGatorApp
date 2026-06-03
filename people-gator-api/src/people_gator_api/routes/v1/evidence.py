import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.engine import get_session
from people_gator_api.db.models.evidence import DerivedEvidence, Evidence
from people_gator_api.schemas.evidence import (
    AuthorityEvidenceIngestRequest,
    BulkAuthorityEvidenceRequest,
    BulkDerivedEvidenceRequest,
    DerivedEvidenceIngestRequest,
    EvidenceIngestResult,
    EvidenceResponse,
    EvidenceReviseRequest,
)
from people_gator_api.services.authz import AuthContext, require_scopes
from people_gator_api.services.evidence_service import (
    get_evidence,
    ingest_authority,
    ingest_derived,
    list_evidence,
)
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter(tags=["evidence"])


@router.post("/evidence/derived", response_model=EvidenceIngestResult, status_code=status.HTTP_201_CREATED)
async def ingest_derived_route(
    payload: DerivedEvidenceIngestRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> EvidenceIngestResult:
    return await ingest_derived(session, payload)


@router.post("/evidence/derived/bulk", response_model=list[EvidenceIngestResult])
async def ingest_derived_bulk_route(
    payload: BulkDerivedEvidenceRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> list[EvidenceIngestResult]:
    if len(payload.items) > 500:
        raise_api_error(422, "batch_too_large", "Maximum batch size is 500")
    return [await ingest_derived(session, item) for item in payload.items]


@router.post("/evidence/derived/{evidence_id}/revise", response_model=EvidenceIngestResult)
async def revise_derived_route(
    evidence_id: uuid.UUID,
    payload: EvidenceReviseRequest,
    auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> EvidenceIngestResult:
    if auth.principal is None:
        raise_api_error(401, "token_missing", "Authentication required")

    evidence = await Evidence.get(session, evidence_id)
    if evidence is None:
        raise_api_error(404, "not_found", "Evidence not found")

    derived = await session.get(DerivedEvidence, evidence_id)
    if derived is None:
        raise_api_error(422, "authority_evidence", "Only derived evidence can be revised")

    assert auth.principal is not None
    evidence.evidence_version_id = payload.evidence_version_id
    derived.revisor_id = auth.principal.principal_id
    derived.revised_metadata = payload.revised_metadata

    return EvidenceIngestResult(
        evidence_id=evidence.evidence_id,
        evidence_version_id=evidence.evidence_version_id,
        status="updated",
    )


@router.options("/evidence/derived/{evidence_id}")
async def options_derived_route(
    evidence_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
) -> dict[str, object]:
    return {
        "evidence_id": str(evidence_id),
        "allowed_methods": ["GET", "HEAD", "OPTIONS", "POST"],
        "allowed_operations": [],
    }


@router.post("/evidence/authority", response_model=EvidenceIngestResult, status_code=status.HTTP_201_CREATED)
async def ingest_authority_route(
    payload: AuthorityEvidenceIngestRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> EvidenceIngestResult:
    return await ingest_authority(session, payload)


@router.post("/evidence/authority/bulk", response_model=list[EvidenceIngestResult])
async def ingest_authority_bulk_route(
    payload: BulkAuthorityEvidenceRequest,
    _auth: AuthContext = Depends(require_scopes("people-gator:ingest")),
    session: AsyncSession = Depends(get_session),
) -> list[EvidenceIngestResult]:
    if len(payload.items) > 500:
        raise_api_error(422, "batch_too_large", "Maximum batch size is 500")
    return [await ingest_authority(session, item) for item in payload.items]


@router.get("/evidence/{evidence_id}", response_model=EvidenceResponse)
async def get_evidence_route(
    evidence_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> EvidenceResponse:
    item = await get_evidence(session, evidence_id)
    if item is None:
        raise_api_error(404, "not_found", "Evidence not found")
    return item


@router.options("/evidence/{evidence_id}")
async def options_evidence_route(
    evidence_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
) -> dict[str, object]:
    return {
        "evidence_id": str(evidence_id),
        "allowed_methods": ["GET", "HEAD", "OPTIONS"],
        "allowed_operations": [],
    }


@router.get("/evidence/{evidence_id}/versions/{evidence_version_id}", response_model=EvidenceResponse)
async def get_evidence_version_route(
    evidence_id: uuid.UUID,
    evidence_version_id: uuid.UUID,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> EvidenceResponse:
    item = await get_evidence(session, evidence_id)
    if item is None or item.evidence_version_id != evidence_version_id:
        raise_api_error(404, "not_found", "Evidence version not found")
    assert item is not None
    return item


@router.get("/evidence", response_model=list[EvidenceResponse])
async def list_evidence_route(
    source_id: uuid.UUID | None = None,
    evidence_type: list[str] = Query(default_factory=list),
    schema_version: str | None = None,
    is_stale: bool = False,
    limit: int = 50,
    after_id: uuid.UUID | None = None,
    _auth: AuthContext = Depends(require_scopes("people-gator:annotate")),
    session: AsyncSession = Depends(get_session),
) -> list[EvidenceResponse]:
    return await list_evidence(
        session=session,
        source_id=source_id,
        evidence_types=evidence_type,
        schema_version=schema_version,
        is_stale=is_stale,
        after_id=after_id,
        limit=limit,
    )
