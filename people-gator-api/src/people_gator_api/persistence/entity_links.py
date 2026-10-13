"""Backend-neutral state transitions; call while holding the annotation lock."""
from datetime import datetime, timezone
from people_gator_api.schemas.enums import EntityLinkState
from people_gator_api.schemas.missing import MISSING, is_missing, missing_to_none


def create_link_state(payload):
    if missing_to_none(payload.entity_id) is None:
        return None
    return EntityLinkState.automatic if is_missing(payload.entity_link_state) else payload.entity_link_state


def link_transition(record, payload, context):
    """Return all four link fields without mutating the record on invalid input."""
    old = (record.entity_id, record.entity_link_state,
           record.entity_link_verified_by_user_id, record.entity_link_verified_at)
    entity = old[0] if is_missing(payload.entity_id) else payload.entity_id
    state = payload.entity_link_state
    if entity is None:
        if not is_missing(state) and state is not None:
            raise ValueError("An unassigned annotation cannot have a link state")
        return (None, None, None, None)
    changed = entity != old[0]
    if state is None:
        raise ValueError("An assigned annotation requires a link state")
    if state == EntityLinkState.verified:
        if changed or old[0] is None:
            raise ValueError("Create the link before verifying it")
        if old[1] == EntityLinkState.verified:
            return old
        return (entity, state, context.user_id, datetime.now(timezone.utc))
    if is_missing(state):
        return (entity, EntityLinkState.manual, None, None) if changed else old
    return (entity, state, None, None)


def apply_link(record, values):
    for field, value in zip(("entity_id", "entity_link_state", "entity_link_verified_by_user_id", "entity_link_verified_at"), values):
        setattr(record, field, value)
