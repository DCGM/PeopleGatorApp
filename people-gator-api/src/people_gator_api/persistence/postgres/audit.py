"""Archive persisted predecessors in the same transaction as repository mutations.

All graph writers take the existing transaction advisory lock before reading the
predecessor. The lock also covers server effects and deletes of dependent rows.
Only selected objects and their deletion/merge dependents are read.
"""

from datetime import datetime, timezone
from functools import wraps
from uuid import UUID, uuid4
from sqlalchemy import select, text, update
from sqlalchemy.orm.attributes import set_committed_value
from people_gator_api.schemas.audit import VersionConflict
from .models import (
    Entity,
    Source,
    ImageOccurrence,
    TextMention,
    AuditChange,
    ObjectHistory,
)
from .touch import lock_annotation_graph

MODELS = {
    "entity": Entity,
    "source": Source,
    "face": ImageOccurrence,
    "mention": TextMention,
}
# Static SQL fragments only; object IDs are always bound parameters.
SNAPSHOTS = {
    "entity": """SELECT e.id, to_jsonb(e) || jsonb_build_object('aliases',
        COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.name) FROM pg_demo_aliases a WHERE a.entity_id=e.id), '[]'::jsonb))
        FROM pg_demo_entities e WHERE e.id = ANY(:ids)""",
    "face": """SELECT e.id, to_jsonb(e) || to_jsonb(f) || jsonb_build_object('embeddings',
        COALESCE((SELECT jsonb_agg(to_jsonb(v) ORDER BY v.model_id) FROM pg_demo_face_embeddings v WHERE v.face_id=e.id), '[]'::jsonb))
        FROM pg_demo_image_occurrences e JOIN pg_demo_faces f USING (id) WHERE e.id = ANY(:ids)""",
    "mention": "SELECT e.id, to_jsonb(e) FROM pg_demo_text_mentions e WHERE e.id = ANY(:ids)",
    "source": """SELECT e.id, to_jsonb(e) || COALESCE(to_jsonb(p), '{}'::jsonb) || COALESCE(to_jsonb(d), '{}'::jsonb)
        FROM pg_demo_sources e LEFT JOIN pg_demo_pages p USING (id) LEFT JOIN pg_demo_documents d USING (id)
        WHERE e.id = ANY(:ids)""",
}


async def snapshots(session, kind, ids):
    if not ids:
        return {}
    return dict(
        (await session.execute(text(SNAPSHOTS[kind]), {"ids": list(ids)})).all()
    )


async def prepare_audit(session, kind, ids, context, expected_versions):
    """Lock/check all explicit targets before any mutation; capture cascade effects."""
    await lock_annotation_graph(session)
    ids = sorted(set(ids))
    model = MODELS[kind]
    await session.execute(
        select(model.id).where(model.id.in_(ids)).order_by(model.id).with_for_update()
    )
    old = await snapshots(session, kind, ids)
    for item_id, state in old.items():
        if expected_versions is None or item_id not in expected_versions:
            raise ValueError(f"expected version required for {kind} {item_id}")
        if expected_versions[item_id] != state["version"]:
            raise VersionConflict(
                f"{kind} {item_id} has changed; reload before editing"
            )
    targets = {kind: old}
    if kind in ("entity", "source"):
        for child_kind, child_model in (
            ("face", ImageOccurrence),
            ("mention", TextMention),
        ):
            reference = (
                child_model.entity_id if kind == "entity" else child_model.source_id
            )
            child_ids = list(
                await session.scalars(select(child_model.id).where(reference.in_(ids)))
            )
            targets[child_kind] = await snapshots(session, child_kind, child_ids)
    # Capture manual portrait invalidation by annotation/source deletion or reassignment.
    if kind != "entity":
        entity_ids = {
            UUID(state["entity_id"])
            for states in targets.values()
            for state in states.values()
            if state.get("entity_id")
        }
        targets["entity"] = await snapshots(session, "entity", entity_ids)
    session.info["audit_pending"] = (targets, context)


def semantic_state(kind, state):
    # Activity propagation is deliberately independent of object content versions.
    result = {
        k: v
        for k, v in state.items()
        if k
        not in (
            "version",
            "last_touched_at",
            "last_touched_by_user_id",
            "last_touched_by_api_key_id",
        )
    }
    if kind == "entity" and state["thumbnail_mode"] == "automatic":
        result.pop("thumbnail_face_id", None)
    return result


async def finish_audit(session):
    pending = session.info.pop("audit_pending", None)
    if pending is None:
        return
    await session.flush()
    targets, actor = pending
    change_id = uuid4()
    histories = []
    versions = {}
    for kind, states in targets.items():
        current = await snapshots(session, kind, states)
        for item_id, old in states.items():
            new = current.get(item_id)
            if new is not None and semantic_state(kind, old) == semantic_state(
                kind, new
            ):
                continue
            histories.append(
                ObjectHistory(
                    object_type=kind,
                    object_id=item_id,
                    version=old["version"],
                    change_id=change_id,
                    deleted=new is None,
                    entity_id=(
                        item_id
                        if kind == "entity"
                        else UUID(old["entity_id"])
                        if old.get("entity_id")
                        else None
                    ),
                    source_id=(
                        item_id
                        if kind == "source"
                        else UUID(old["source_id"])
                        if old.get("source_id")
                        else None
                    ),
                    state=old,
                )
            )
            if new is not None:
                version = old["version"] + 1
                model = MODELS[kind]
                await session.execute(
                    update(model).where(model.id == item_id).values(version=version)
                )
                versions[kind, item_id] = version
    if histories:
        session.add(
            AuditChange(
                id=change_id,
                changed_at=datetime.now(timezone.utc),
                actor_user_id=actor.user_id,
                actor_api_key_id=getattr(actor, "api_key_id", None),
            )
        )
        await session.flush()
        session.add_all(histories)
    for obj in session.identity_map.values():
        kind = (
            "entity"
            if isinstance(obj, Entity)
            else "source"
            if isinstance(obj, Source)
            else "face"
            if isinstance(obj, ImageOccurrence)
            else "mention"
            if isinstance(obj, TextMention)
            else None
        )
        if kind is not None and (kind, obj.id) in versions:
            set_committed_value(obj, "version", versions[kind, obj.id])


def audit_transaction(method):
    """Ensure validation, conflicts and injected failures discard the whole mutation."""

    @wraps(method)
    async def wrapped(self, *args, **kwargs):
        try:
            return await method(self, *args, **kwargs)
        except Exception:
            await self._session.rollback()
            raise
        finally:
            if self._session.info.pop("audit_pending", None) is not None:
                await self._session.rollback()

    return wrapped
