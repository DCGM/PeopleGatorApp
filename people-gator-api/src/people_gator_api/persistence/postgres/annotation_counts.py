"""One grouped UNION ALL, never a face × mention join or a query per result.

This projection uses the response summaries' source scope. Only count-aware
queries pay for it; no evidence filter can narrow the counted annotations.
"""

from sqlalchemy import func, literal, select, union_all
from people_gator_api.schemas.annotation_counts import ANNOTATION_COUNT_FIELDS
from people_gator_api.schemas.missing import missing_to_none
from .entity_link_queries import source_scope
from .models import Source, ImageOccurrence, TextMention


def annotation_counts():
    evidence = union_all(
        select(
            ImageOccurrence.source_id,
            ImageOccurrence.entity_link_state.label("state"),
            literal("faces").label("kind"),
        ).where(ImageOccurrence.occurrence_type == "face"),
        select(
            TextMention.source_id, TextMention.entity_link_state, literal("mentions")
        ),
    ).subquery("counted_annotations")
    scope = source_scope()
    columns = []
    for field in ANNOTATION_COUNT_FIELDS:
        category, state, _ = field.split("_")
        conditions = [] if category == "annotations" else [evidence.c.kind == category]
        if state != "total":
            conditions.append(
                evidence.c.state.is_(None)
                if state == "unassigned"
                else evidence.c.state == state
            )
        columns.append(
            func.count().filter(*conditions).label(field)
            if conditions
            else func.count().label(field)
        )
    return (
        select(scope.c.owner_id, *columns)
        .select_from(scope)
        .join(evidence, evidence.c.source_id == scope.c.source_id)
        .group_by(scope.c.owner_id)
        .cte()
    )


def count_column(counts, field):
    # No evidence means a known zero, including for empty documents/pages.
    return func.coalesce(counts.c[field], 0)


def count_minima(values):
    if values is None:
        return {}
    return {
        field: value
        for field in ANNOTATION_COUNT_FIELDS
        if (value := missing_to_none(getattr(values, "min_" + field))) is not None
        and value > 0
    }


def minimum_count_predicate(values):
    minima = count_minima(values)
    if not minima:
        return None
    counts = annotation_counts()
    # Positive minima exclude missing (zero) rows without an outer join.
    return Source.id.in_(
        select(counts.c.owner_id).where(
            *(counts.c[field] >= value for field, value in minima.items())
        )
    )
