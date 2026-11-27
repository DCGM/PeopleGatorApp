"""Publish what mutation routes changed to the live event hub.

Routes call the ``previous_*`` helpers before a write that can move or remove
a link, then a ``publish_*`` helper after the repository committed. While
nobody is subscribed the helpers return immediately without database access.
"""

import uuid
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence

from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.events import ChangeKind, TopicKind
from people_gator_api.schemas.faces import FaceResponse
from people_gator_api.schemas.mentions import TextMentionResponse
from people_gator_api.schemas.sources import DocumentLookupRequest, PageResponse
from people_gator_api.services.event_service import ChangeSet, EventHub


type Link = FaceResponse | TextMentionResponse
type Links = Mapping[uuid.UUID, Link]

NO_LINKS: Links = {}


def _link_id(link: Link) -> uuid.UUID:
    return link.detection_id if isinstance(link, FaceResponse) else link.mention_id


async def _previous[T: Link](
    hub: EventHub,
    get: Callable[[uuid.UUID], Awaitable[T | None]],
    ids: Iterable[uuid.UUID],
) -> dict[uuid.UUID, T]:
    if not hub.active:
        return {}
    found: dict[uuid.UUID, T] = {}
    for object_id in dict.fromkeys(ids):
        if (link := await get(object_id)) is not None:
            found[object_id] = link
    return found


async def previous_faces(
    hub: EventHub, database: Database, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, FaceResponse]:
    """Read faces before a patch or delete, to notify their old entity and source."""
    return await _previous(hub, database.faces.get, ids)


async def previous_mentions(
    hub: EventHub, database: Database, ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, TextMentionResponse]:
    """Read mentions before a patch or delete, to notify their old entity and source."""
    return await _previous(hub, database.text_mentions.get, ids)


def publish_links(
    hub: EventHub,
    kind: TopicKind,
    change: ChangeKind,
    links: Iterable[Link | None],
    previous: Links = NO_LINKS,
) -> None:
    """Notify created or updated faces/mentions, their source and old/new entity."""
    if not hub.active:
        return
    changes = ChangeSet()
    for link in links:
        if link is None:
            continue
        before = previous.get(_link_id(link))
        changes.link(
            kind,
            change,
            _link_id(link),
            link.source_id,
            link.entity_id,
            before.entity_id if before is not None else None,
        )
    hub.publish(changes)


def publish_deleted_links(hub: EventHub, kind: TopicKind, previous: Links) -> None:
    """Notify deleted faces/mentions from their state read before the delete."""
    publish_links(hub, kind, ChangeKind.DELETED, previous.values())


def publish_entities(
    hub: EventHub, change: ChangeKind, entity_ids: Iterable[uuid.UUID]
) -> None:
    if not hub.active:
        return
    changes = ChangeSet()
    for entity_id in entity_ids:
        changes.entity(change, entity_id)
    hub.publish(changes)


def publish_bulk_delete(hub: EventHub, kind: TopicKind, deleted_count: int) -> None:
    """Notify the kind-wide topic of a filtered delete that reports only a count."""
    if not deleted_count or not hub.active:
        return
    changes = ChangeSet()
    changes.several(kind, ChangeKind.DELETED)
    hub.publish(changes)


def publish_merge(
    hub: EventHub, target_id: uuid.UUID, merged_ids: Iterable[uuid.UUID]
) -> None:
    if not hub.active:
        return
    changes = ChangeSet()
    changes.merge(target_id, merged_ids)
    hub.publish(changes)


async def document_source_ids(
    hub: EventHub, database: Database, pages: Sequence[PageResponse]
) -> dict[uuid.UUID, uuid.UUID]:
    """Map page source IDs to their registered document's source ID."""
    if not hub.active:
        return {}
    documents: dict[tuple[str, uuid.UUID], uuid.UUID | None] = {}
    parents: dict[uuid.UUID, uuid.UUID] = {}
    for page in pages:
        key = (page.library, page.document_id)
        if key not in documents:
            document = await database.sources.lookup_document(
                DocumentLookupRequest(library=page.library, document_id=page.document_id)
            )
            documents[key] = document.source_id if document is not None else None
        if (parent := documents[key]) is not None:
            parents[page.source_id] = parent
    return parents


async def page_parent(
    hub: EventHub, database: Database, source_id: uuid.UUID
) -> dict[uuid.UUID, uuid.UUID]:
    """Map a source that is a page to its document's source ID."""
    if not hub.active:
        return {}
    page = await database.sources.get_page(source_id)
    return await document_source_ids(hub, database, [page]) if page is not None else {}


def publish_sources(
    hub: EventHub,
    change: ChangeKind,
    source_ids: Iterable[uuid.UUID],
    parents: Mapping[uuid.UUID, uuid.UUID] | None = None,
) -> None:
    """Notify sources; pages listed in ``parents`` also notify their document."""
    if not hub.active:
        return
    changes = ChangeSet()
    for source_id in source_ids:
        changes.source(change, source_id, (parents or {}).get(source_id))
    hub.publish(changes)
