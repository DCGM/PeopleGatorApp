"""Shared document scope, same-witness filters and batched link aggregates."""
from sqlalchemy import select, union_all, or_, exists, func
from people_gator_api.schemas.entity_links import EntityLinkStats
from .models import Source, Document, Page, Entity, ImageOccurrence, TextMention


def source_scope():
    # A document owns its direct annotations and registered pages in its library.
    document = Document.__table__.alias("scope_document")
    page = Page.__table__.alias("scope_page")
    source = Source.__table__.alias("scope_source")
    return union_all(
        select(source.c.id.label("owner_id"), source.c.id.label("source_id")),
        select(document.c.id, page.c.id).select_from(document.join(page,
            (document.c.library == page.c.library) & (document.c.document_id == page.c.document_id)))
    ).subquery("annotation_scope")


def document_sources(ids):
    scope = source_scope()
    return select(scope.c.source_id).where(scope.c.owner_id.in_(ids))


def evidence_predicate(filter_values, *, entity=False):
    """All related evidence constraints must be satisfied by the same link.

    Explicit face AND mention requirements stay AND; otherwise either kind is
    sufficient. Presence flags are deliberately handled by their original code.
    """
    from people_gator_api.schemas.missing import missing_to_none
    states = missing_to_none(filter_values.entity_link_state)
    face_ids = missing_to_none(filter_values.detection_id)
    mention_ids = missing_to_none(filter_values.mention_id)
    scope = source_scope()
    source_ids = missing_to_none(getattr(filter_values, "source_id", None)) if entity else None
    document_ids = missing_to_none(getattr(filter_values, "document_source_id", None)) if entity else None
    entity_ids = missing_to_none(filter_values.entity_id) if not entity else None
    predicates = []
    selections = []
    for model, ids in ((ImageOccurrence, face_ids), (TextMention, mention_ids)):
        conditions = []
        if model is ImageOccurrence:
            conditions.append(model.occurrence_type == "face")
        if entity:
            conditions.append(model.entity_id.is_not(None))
            if source_ids is not None:
                conditions.append(model.source_id.in_(source_ids))
            if document_ids is not None:
                conditions.append(model.source_id.in_(document_sources(document_ids)))
        else:
            conditions.append(exists(select(1).select_from(scope).where(
                scope.c.owner_id == Source.id, scope.c.source_id == model.source_id
            ).correlate(Source, model)))
            if entity_ids is not None:
                conditions.append(model.entity_id.in_(entity_ids))
        if states is not None:
            conditions.append(model.entity_link_state.in_(states))
        if ids is not None:
            conditions.append(model.id.in_(ids))
        selection = select(model.entity_id).where(*conditions)
        selections.append(selection)
        predicate = Entity.id.in_(selection) if entity else exists(select(1).select_from(model).where(*conditions))
        predicates.append(predicate)
    if face_ids is not None and mention_ids is not None:
        return predicates[0] & predicates[1]
    if face_ids is not None:
        return predicates[0]
    if mention_ids is not None:
        return predicates[1]
    return Entity.id.in_(union_all(*selections)) if entity else or_(*predicates)


async def load_link_stats(session, objects, *, entities=False):
    """Two grouped queries for a response page, never a query per card."""
    objects = list(objects)
    if not objects:
        return
    stats = {obj.id: EntityLinkStats() for obj in objects}
    for model, kind in ((ImageOccurrence, "faces"), (TextMention, "mentions")):
        conditions = [model.occurrence_type == "face"] if kind == "faces" else []
        if entities:
            key = model.entity_id
            statement = select(key, model.entity_link_state, func.count()).where(key.in_(stats), *conditions)
        else:
            scope = source_scope()
            key = scope.c.owner_id
            statement = select(key, model.entity_link_state, func.count()).select_from(model).join(
                scope, scope.c.source_id == model.source_id
            ).where(key.in_(stats), *conditions)
        rows = await session.execute(statement.group_by(key, model.entity_link_state))
        for owner, state, count in rows:
            counts = getattr(stats[owner], kind)
            setattr(counts, state.value if state is not None else "unassigned", count)
            counts.total += count
    for obj in objects:
        obj._entity_link_stats = stats[obj.id]
