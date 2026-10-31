"""Entity-wide assigned annotation totals, grouped once without evidence cross products."""

from sqlalchemy import BigInteger, func, literal, select, union_all
from .models import Entity, ImageOccurrence, TextMention
from .annotation_counts import count_column
from people_gator_api.schemas.missing import missing_to_none


def entity_counts():
    evidence = union_all(
        select(ImageOccurrence.entity_id.label("owner_id"), literal("faces").label("kind"))
        .where(ImageOccurrence.occurrence_type == "face", ImageOccurrence.entity_id.is_not(None)),
        select(TextMention.entity_id, literal("mentions"))
        .where(TextMention.entity_id.is_not(None)),
    ).subquery("entity_counted_evidence")
    return select(
        evidence.c.owner_id,
        func.count(type_=BigInteger).filter(evidence.c.kind == "faces").label("faces_total_count"),
        func.count(type_=BigInteger).filter(evidence.c.kind == "mentions").label("mentions_total_count"),
        func.count(type_=BigInteger).label("annotations_total_count"),
    ).group_by(evidence.c.owner_id).cte()


def entity_count_predicate(values):
    bounds = {}
    for kind in ("faces", "mentions"):
        for bound in ("min", "max"):
            name = f"{bound}_{kind}_total_count"
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
