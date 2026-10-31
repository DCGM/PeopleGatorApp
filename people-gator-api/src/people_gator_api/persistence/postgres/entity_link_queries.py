"""Shared document scope, same-witness filters and batched link aggregates."""

from sqlalchemy import tuple_, select, union_all, or_, exists, func
from people_gator_api.schemas.entity_links import EntityLinkStats
from .models import Source, Document, Page, Entity, ImageOccurrence, TextMention, User, APIKey


def source_scope():
    # A document owns its direct annotations and registered pages in its library.
    document = Document.__table__.alias("scope_document")
    page = Page.__table__.alias("scope_page")
    source = Source.__table__.alias("scope_source")
    return union_all(
        select(source.c.id.label("owner_id"), source.c.id.label("source_id")),
        select(document.c.id, page.c.id).select_from(
            document.join(
                page,
                (document.c.library == page.c.library)
                & (document.c.document_id == page.c.document_id),
            )
        ),
    ).subquery("annotation_scope")


def document_sources(ids):
    scope = source_scope()
    document = Document.__table__
    return select(scope.c.source_id).where(
        scope.c.owner_id.in_(select(document.c.id).where(document.c.id.in_(ids)))
    )


def library_sources(libraries):
    return union_all(
        select(Page.__table__.c.id).where(Page.__table__.c.library.in_(libraries)),
        select(Document.__table__.c.id).where(Document.__table__.c.library.in_(libraries)),
    )


def page_sources(ids):
    """Resolve only registered pages; document/image UUIDs cannot select a page."""
    page = Page.__table__
    return select(page.c.id).where(page.c.id.in_(ids))


SCOPE_FIELDS = ("library", "document_source_id", "page_source_id")
LINK_FIELDS = ("entity_link_state", *SCOPE_FIELDS)


def scope_conditions(source_id, values):
    """Membership of a source in the selected library, document and page scope."""
    from people_gator_api.schemas.missing import missing_to_none
    conditions = []
    libraries = missing_to_none(values.library)
    if libraries is not None:
        conditions.append(source_id.in_(library_sources(libraries)))
    documents = missing_to_none(values.document_source_id)
    if documents is not None:
        conditions.append(source_id.in_(document_sources(documents)))
    pages = missing_to_none(values.page_source_id)
    if pages is not None:
        conditions.append(source_id.in_(page_sources(pages)))
    return conditions


def touch_conditions(model, values):
    """The latest recorded change of the filtered record itself."""
    from people_gator_api.schemas.missing import missing_to_none
    conditions = []
    for field, column in (("last_touched_by_user_id", model.last_touched_by_user_id),
                          ("last_touched_by_api_key_id", model.last_touched_by_api_key_id)):
        value = missing_to_none(getattr(values, field))
        if value is not None:
            conditions.append(column.in_(value))
    for field, op in (("last_touched_from", model.last_touched_at.__ge__),
                      ("last_touched_to", model.last_touched_at.__le__)):
        value = missing_to_none(getattr(values, field))
        if value is not None:
            conditions.append(op(value))
    return conditions


def annotation_conditions(model, values):
    """Link state and source scope of one face/mention annotation."""
    from people_gator_api.schemas.missing import missing_to_none
    conditions = scope_conditions(model.source_id, values)
    states = missing_to_none(values.entity_link_state)
    if states is not None:
        conditions.append(model.entity_link_state.in_(states))
    return conditions


def evidence_predicate(filter_values, *, entity=False):
    """All related evidence constraints must be satisfied by the same link.

    Explicit face AND mention requirements stay AND; otherwise either kind is
    sufficient. Presence flags are deliberately handled by their original code.
    """
    from people_gator_api.schemas.missing import missing_to_none

    face_ids = missing_to_none(filter_values.detection_id)
    mention_ids = missing_to_none(filter_values.mention_id)
    scope = source_scope()
    source_ids = (
        missing_to_none(getattr(filter_values, "source_id", None)) if entity else None
    )
    entity_ids = missing_to_none(filter_values.entity_id) if not entity else None
    predicates = []
    selections = []
    for model, ids in ((ImageOccurrence, face_ids), (TextMention, mention_ids)):
        conditions = annotation_conditions(model, filter_values)
        if model is ImageOccurrence:
            conditions.append(model.occurrence_type == "face")
        if entity:
            conditions.append(model.entity_id.is_not(None))
            if source_ids is not None:
                conditions.append(model.source_id.in_(source_ids))
        else:
            conditions.append(
                exists(
                    select(1)
                    .select_from(scope)
                    .where(
                        scope.c.owner_id == Source.id,
                        scope.c.source_id == model.source_id,
                    )
                    .correlate(Source, model)
                )
            )
            if entity_ids is not None:
                conditions.append(model.entity_id.in_(entity_ids))
        if ids is not None:
            conditions.append(model.id.in_(ids))
        selection = select(model.entity_id).where(*conditions)
        selections.append(selection)
        predicate = (
            Entity.id.in_(selection)
            if entity
            else exists(select(1).select_from(model).where(*conditions))
        )
        predicates.append(predicate)
    wants_faces = face_ids is not None or getattr(filter_values, "has_detections", None) is True or getattr(filter_values, "has_faces", None) is True
    wants_mentions = mention_ids is not None or getattr(filter_values, "has_mentions", None) is True
    if wants_faces and wants_mentions:
        return predicates[0] & predicates[1]
    if wants_faces:
        return predicates[0]
    if wants_mentions:
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
            statement = select(key, model.entity_link_state, func.count()).where(
                key.in_(stats), *conditions
            )
        else:
            scope = source_scope()
            key = scope.c.owner_id
            statement = (
                select(key, model.entity_link_state, func.count())
                .select_from(model)
                .join(scope, scope.c.source_id == model.source_id)
                .where(key.in_(stats), *conditions)
            )
        rows = await session.execute(statement.group_by(key, model.entity_link_state))
        for owner, state, count in rows:
            counts = getattr(stats[owner], kind)
            setattr(counts, state.value if state is not None else "unassigned", count)
            counts.total += count
    for obj in objects:
        obj._entity_link_stats = stats[obj.id]
    if not entities:
        pages = [obj for obj in objects if isinstance(obj, Page)]
        if pages:
            identities = {(obj.library, obj.document_id) for obj in pages}
            rows = await session.execute(select(Page.library, Page.document_id, func.count()).where(tuple_(Page.library, Page.document_id).in_(identities)).group_by(Page.library, Page.document_id))
            counts = {(library, document): count for library, document, count in rows}
            for obj in pages:
                obj._registered_page_count = counts.get((obj.library, obj.document_id), 0)
        await load_document_summaries(session, objects)


async def load_document_summaries(session, objects):
    """Three bounded batch queries, with no page/evidence Cartesian product."""
    documents = {obj.id: obj for obj in objects if isinstance(obj, Document)}
    if not documents:
        return
    for obj in documents.values():
        obj._document_summary = {"registered_page_count": 0, "linked_entity_count": 0, "first_page_source_id": None, "first_page_number": None}
    document, page = Document.__table__.c, Page.__table__.c
    pages = (
        # Count before DISTINCT ON selects the first numbered page for each document.
        select(document.id, func.count(page.id).over(partition_by=document.id), page.id, page.page_number)
        .select_from(Document.__table__.join(Page.__table__,
            (page.library == document.library) & (page.document_id == document.document_id)))
        .where(document.id.in_(documents)).distinct(document.id).order_by(document.id, page.page_number.asc().nulls_last(), page.id)
    )
    for owner, count, first_page, number in await session.execute(pages):
        documents[owner]._document_summary.update(registered_page_count=count, first_page_source_id=first_page, first_page_number=number)
    scope = source_scope()
    evidence = union_all(
        select(ImageOccurrence.source_id, ImageOccurrence.entity_id).where(ImageOccurrence.occurrence_type == "face"),
        select(TextMention.source_id, TextMention.entity_id),
    ).subquery("linked_evidence")
    linked = (
        select(scope.c.owner_id, func.count(func.distinct(evidence.c.entity_id)))
        .select_from(scope).join(evidence, evidence.c.source_id == scope.c.source_id)
        .where(scope.c.owner_id.in_(documents)).group_by(scope.c.owner_id)
    )
    for owner, count in await session.execute(linked):
        documents[owner]._document_summary["linked_entity_count"] = count
    attribution = (
        select(Source.id, User.display_name, APIKey.display_name)
        .outerjoin(User, User.id == Source.last_touched_by_user_id)
        .outerjoin(APIKey, APIKey.id == Source.last_touched_by_api_key_id)
        .where(Source.id.in_(documents))
    )
    for owner, user, key in await session.execute(attribution):
        documents[owner]._document_summary.update(
            last_touched_by_user_name=user, last_touched_by_api_key_name=key,
        )
