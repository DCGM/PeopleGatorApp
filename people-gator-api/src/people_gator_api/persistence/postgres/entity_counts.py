"""Entity-wide assigned annotation totals, grouped once without evidence cross products."""

from sqlalchemy import BigInteger, func, literal, select, union_all
from .models import Entity, ImageOccurrence, TextMention
from .annotation_counts import count_column
from people_gator_api.schemas.missing import missing_to_none
from people_gator_api.schemas.entity_counts import ENTITY_COUNT_FIELDS


def entity_counts():
    evidence = union_all(
        select(ImageOccurrence.entity_id.label("owner_id"), literal("faces").label("kind"), ImageOccurrence.entity_link_state.label("state"))
        .where(ImageOccurrence.occurrence_type == "face", ImageOccurrence.entity_id.is_not(None)),
        select(TextMention.entity_id, literal("mentions"), TextMention.entity_link_state)
        .where(TextMention.entity_id.is_not(None)),
    ).subquery("entity_counted_evidence")
    columns = []
    for field in ENTITY_COUNT_FIELDS:
        category, state, _ = field.split("_")
        conditions = [] if category == "annotations" else [evidence.c.kind == category]
        if state != "total":
            conditions.append(evidence.c.state == state)
        columns.append(func.count(type_=BigInteger).filter(*conditions).label(field)
                       if conditions else func.count(type_=BigInteger).label(field))
    return select(evidence.c.owner_id, *columns).group_by(evidence.c.owner_id).cte()



def entity_count_predicate(values):
    bounds = {}
    for field in ENTITY_COUNT_FIELDS:
        for bound in ("min", "max"):
            name = f"{bound}_{field}"
            value = missing_to_none(getattr(values, name))
            if value is not None and (bound == "max" or value > 0):
                bounds[name] = value
    if not bounds:
        return None
    counts = entity_counts()
    conditions = []
    for name, value in bounds.items():
        bound, field = name.split("_", 1)
        column = count_column(counts, field)
        conditions.append(column >= value if bound == "min" else column <= value)
    owners = Entity.__table__.alias("counted_entity_owners")
    return Entity.id.in_(select(owners.c.id).outerjoin(
        counts, counts.c.owner_id == owners.c.id,
    ).where(*conditions))
