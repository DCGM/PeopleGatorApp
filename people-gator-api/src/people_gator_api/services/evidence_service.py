import uuid

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.db.models.enums import EvidenceType
from people_gator_api.db.models.evidence import (
    AuthorityIdentifierEvidence,
    Evidence,
    FaceDetectionEvidence,
    GroundedDescriptionEvidence,
    GroundedNameEvidence,
    NamedEntityEvidence,
    TextRegionEvidence,
)
from people_gator_api.schemas.evidence import (
    AuthorityEvidenceIngestRequest,
    DerivedEvidenceIngestRequest,
    EvidenceIngestResult,
    EvidenceResponse,
)


def _to_response(item: Evidence) -> EvidenceResponse:
    return EvidenceResponse(
        evidence_id=item.evidence_id,
        evidence_version_id=item.evidence_version_id,
        source_id=item.source_id,
        source_path=item.source_path,
        evidence_type=item.evidence_type,
        schema_version=item.schema_version,
        content_hash=item.content_hash,
        is_deleted=item.is_deleted,
        is_stale=item.is_stale,
    )


def _new_derived_record(
    evidence_id: uuid.UUID,
    evidence_type: EvidenceType,
    producer_id: uuid.UUID,
    produced_metadata: dict[str, object],
) -> FaceDetectionEvidence | NamedEntityEvidence | TextRegionEvidence:
    if evidence_type == EvidenceType.face_detection:
        return FaceDetectionEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            produced_metadata=produced_metadata,
            revisor_id=None,
            revised_metadata=None,
        )
    if evidence_type == EvidenceType.named_entity:
        return NamedEntityEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            produced_metadata=produced_metadata,
            revisor_id=None,
            revised_metadata=None,
        )
    if evidence_type == EvidenceType.text_region:
        return TextRegionEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            produced_metadata=produced_metadata,
            revisor_id=None,
            revised_metadata=None,
        )
    raise ValueError(f"unsupported_derived_evidence_type:{evidence_type.value}")


def _new_authority_record(
    evidence_id: uuid.UUID,
    evidence_type: EvidenceType,
    producer_id: uuid.UUID,
    metadata: dict[str, object],
) -> GroundedNameEvidence | GroundedDescriptionEvidence | AuthorityIdentifierEvidence:
    if evidence_type == EvidenceType.grounded_name:
        return GroundedNameEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            metadata_=metadata,
        )
    if evidence_type == EvidenceType.grounded_description:
        return GroundedDescriptionEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            metadata_=metadata,
        )
    if evidence_type == EvidenceType.authority_identifier:
        return AuthorityIdentifierEvidence(
            evidence_id=evidence_id,
            producer_id=producer_id,
            metadata_=metadata,
        )
    raise ValueError(f"unsupported_authority_evidence_type:{evidence_type.value}")


async def ingest_derived(
    session: AsyncSession,
    payload: DerivedEvidenceIngestRequest,
) -> EvidenceIngestResult:
    evidence_id = payload.evidence_id or uuid.uuid4()

    existing = await Evidence.get(session, evidence_id)
    if existing is not None and existing.content_hash == payload.content_hash:
        return EvidenceIngestResult(
            evidence_id=existing.evidence_id,
            evidence_version_id=existing.evidence_version_id,
            status="unchanged",
        )

    evidence_version_id = uuid.uuid4()
    base = Evidence(
        evidence_id=evidence_id,
        evidence_version_id=evidence_version_id,
        evidence_type=payload.evidence_type,
        schema_version=payload.schema_version,
        source_id=payload.source_id,
        source_path=payload.source_path,
        content_hash=payload.content_hash,
        is_deleted=False,
        is_stale=False,
    )
    session.add(base)

    derived = _new_derived_record(
        evidence_id=evidence_id,
        evidence_type=payload.evidence_type,
        producer_id=payload.producer_id,
        produced_metadata=payload.produced_metadata,
    )
    session.add(derived)

    return EvidenceIngestResult(
        evidence_id=evidence_id,
        evidence_version_id=evidence_version_id,
        status="created" if existing is None else "updated",
    )


async def ingest_authority(
    session: AsyncSession,
    payload: AuthorityEvidenceIngestRequest,
) -> EvidenceIngestResult:
    evidence_id = payload.evidence_id or uuid.uuid4()

    existing = await Evidence.get(session, evidence_id)
    if existing is not None and existing.content_hash == payload.content_hash:
        return EvidenceIngestResult(
            evidence_id=existing.evidence_id,
            evidence_version_id=existing.evidence_version_id,
            status="unchanged",
        )

    evidence_version_id = uuid.uuid4()
    base = Evidence(
        evidence_id=evidence_id,
        evidence_version_id=evidence_version_id,
        evidence_type=payload.evidence_type,
        schema_version=payload.schema_version,
        source_id=payload.source_id,
        source_path=payload.source_path,
        content_hash=payload.content_hash,
        is_deleted=False,
        is_stale=False,
    )
    session.add(base)

    authority = _new_authority_record(
        evidence_id=evidence_id,
        evidence_type=payload.evidence_type,
        producer_id=payload.producer_id,
        metadata=payload.metadata,
    )
    session.add(authority)

    return EvidenceIngestResult(
        evidence_id=evidence_id,
        evidence_version_id=evidence_version_id,
        status="created" if existing is None else "updated",
    )


async def get_evidence(session: AsyncSession, evidence_id: uuid.UUID) -> EvidenceResponse | None:
    item = await Evidence.get(session, evidence_id)
    if item is None:
        return None
    return _to_response(item)


async def list_evidence(
    session: AsyncSession,
    source_id: uuid.UUID | None,
    evidence_types: list[str],
    schema_version: str | None,
    is_stale: bool,
    after_id: uuid.UUID | None,
    limit: int,
) -> list[EvidenceResponse]:
    stmt = sa.select(Evidence).order_by(Evidence.evidence_id.asc()).limit(limit)
    if source_id is not None:
        stmt = stmt.where(Evidence.source_id == source_id)
    if evidence_types:
        stmt = stmt.where(Evidence.evidence_type.in_(evidence_types))
    if schema_version is not None:
        stmt = stmt.where(Evidence.schema_version == schema_version)
    if not is_stale:
        stmt = stmt.where(Evidence.is_stale.is_(False))
    if after_id is not None:
        stmt = stmt.where(Evidence.evidence_id > after_id)

    result = await session.execute(stmt)
    return [_to_response(item) for item in result.scalars().all()]
