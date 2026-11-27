# Live change events

Clients learn that objects they show were changed by someone else through one
Server-Sent Events stream per session. An event only says *what* changed;
it carries no data, so the client refetches. All three routes need
`people-gator:browse`.

| Route | Purpose |
| --- | --- |
| `GET /api/v1/events/{session_id}` | Stream the session's events (`text/event-stream`) |
| `PATCH /api/v1/events/{session_id}/topics` | Subscribe and unsubscribe topics |
| `GET /api/v1/events/{session_id}/topics` | List the session's topics |

## Sessions

The client picks a random UUID as its session ID. Either route creates the
session on first use, owned by the calling user; another user gets 404.
A session has one stream: opening a second one ends the first.

Subscriptions belong to the session, not to the connection, so they survive a
reconnect. A session without a stream is forgotten after 60 seconds, and all
sessions are lost when the API restarts. A user can hold 16 sessions; beyond
that the longest-idle one is dropped, or the request returns 429 when all are
connected.

## Topics

A topic is `{"kind", "id", "scope"}`.

| Topic | Follows |
| --- | --- |
| `{"kind": "entity", "id": E}` | The entity itself (people are entities): created, edited, merged into, deleted |
| `{"kind": "entity", "id": E, "scope": "related"}` | Faces and text mentions linked to the entity, including links moved to or away from it |
| `{"kind": "source", "id": S}` | The document, page or image itself, including a page's uploaded scan or layout |
| `{"kind": "source", "id": S, "scope": "related"}` | Faces and text mentions on the source, and the pages of a document |
| `{"kind": "face", "id": F}` | One face |
| `{"kind": "mention", "id": M}` | One text mention |
| `{"kind": K}` (no `id`) | Every object of that kind, for example newly created entities |

`scope` defaults to `self`. Source IDs are source UUIDs, not archive document or
page UUIDs. A session holds at most 1000 topics.

```sh
curl -X PATCH "$API/api/v1/events/$SESSION/topics" -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{
    "subscribe": [{"kind": "source", "id": "'$PAGE'", "scope": "related"}],
    "unsubscribe": [{"kind": "entity", "id": "'$PERSON'"}]
  }'
```

Unsubscribing is applied first. Repeating a subscription or removing an unknown
topic changes nothing. The response lists the resulting topics.

## Stream

Every frame is a default (`message`) SSE event whose `data` is JSON. The first
frame of each connection is the session:

```json
{"type": "session", "session_id": "…", "topics": [{"kind": "face", "id": "…", "scope": "self"}]}
```

Every later frame is one change of one subscribed topic:

```json
{"type": "change",
 "topic": {"kind": "entity", "id": "…", "scope": "related"},
 "change": "updated",
 "object": {"kind": "mention", "id": "…"}}
```

- `change` is `created`, `updated` or `deleted` and describes `object`.
- `object` names the changed object. It is `null` on a `related` or kind-wide
  topic when one request changed several objects; refetch the list.
- One request sends at most one event per topic. A session subscribed to
  several matching topics receives one event for each.

Reassigning a mention from person A to person B therefore sends `updated` to the
mention, to its source's `related` topic and to the `related` topics of both A
and B.

The server sends a `: ping` comment every 15 seconds. The browser `EventSource`
cannot send the `Authorization` header; use a `fetch`-based reader such as the
generated client's `streamEventsRouteApiV1EventsSessionIdGet`.

## What a client must handle

Delivery is best effort and nothing is replayed.

- **On every `session` frame** (first connect and each reconnect) refetch what
  is shown, and re-subscribe if `topics` is missing entries.
- A client that falls 1000 events behind is disconnected and should reconnect.
- **Cascades reach the parent, not each child.** Deleting or merging an entity
  sends `deleted` to its own and its `related` topic, and a merge sends one
  `updated` with `object: null` to the target's `related` topic; the moved
  faces and mentions get no event of their own. Deleting a source likewise
  notifies the source and its `related` topic, not its faces, mentions or the
  entities they were linked to.
- `DELETE /api/v1/entities` (by filter) only notifies the kind-wide entity topic.
- An unchanged write still sends `updated`.
- Only writes through this API process are seen: not the seed, migrations or
  maintenance commands. The hub lives in process memory, like refresh sessions,
  so several workers would need routing to one worker.
- An open stream is not closed when its access token expires.

Publishing is implemented in `services/event_service.py` (hub) and
`routes/v1/change_events.py` (what each write notifies). While no session is
subscribed, writes do no extra work.
