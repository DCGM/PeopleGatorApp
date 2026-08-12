# Server-Sent Events

This document describes the current server-sent events (SSE) implementation in People Gator API. It covers the HTTP subscription endpoint, the internal broker interface, topic hierarchy, event names, payloads, producer integration, lifecycle behavior, and the constraints of the local implementation.

## Overview

The SSE service has two separate responsibilities:

1. `EventSourceResponse` keeps an HTTP response open and streams events to a client.
2. `TopicBroker` routes typed events from producers to subscribed consumers.

The current broker is `LocalTopicBroker`. It stores subscriptions in process memory and uses an `asyncio.Queue` for every consumer. The broker interface is deliberately transport-oriented so a future Redis or other distributed implementation can replace it without changing route code.

The event flow is:

```text
CRUD endpoint or other producer
        |
        | publish(topic, event, data)
        v
    TopicBroker
        |
        | fan out to exact topic and ancestors
        v
    asyncio.Queue per subscriber
        |
        | async iteration
        v
    EventSourceResponse
        |
        v
    SSE client
```

## HTTP Endpoint

The service exposes explicit subscription endpoints. It does not accept an arbitrary topic path.

The admin statistics endpoint is:

```text
GET /api/v1/sse/
```

It requires the `people-gator:admin` scope and returns the active subscriber count for each concrete topic in the current process plus the total count:

```json
{
    "topics": {
        "entities/0194f5c6-...": 2,
        "entities": 1
    },
    "total_subscribers": 3
}
```

Subscription routes are registered under the versioned API router, so their complete paths are `/api/v1/sse/...`.

Collection subscriptions:

```text
GET /api/v1/sse/entities
GET /api/v1/sse/faces
GET /api/v1/sse/page-mentions
GET /api/v1/sse/document-mentions
GET /api/v1/sse/principals
GET /api/v1/sse/model-agents
GET /api/v1/sse/users
GET /api/v1/sse/sources
```

Resource subscriptions:

```text
GET /api/v1/sse/entities/{entity_id}
GET /api/v1/sse/faces/{detection_id}
GET /api/v1/sse/page-mentions/{page_mention_id}
GET /api/v1/sse/document-mentions/{document_mention_id}
GET /api/v1/sse/principals/{principal_id}
GET /api/v1/sse/model-agents/{principal_id}
GET /api/v1/sse/users/{principal_id}
GET /api/v1/sse/sources/{source_id}
```

Relationship subscriptions are available for the relationships currently published by mutation routes:

```text
GET /api/v1/sse/entities/{entity_id}/faces
GET /api/v1/sse/entities/{entity_id}/document-mentions
GET /api/v1/sse/entities/{entity_id}/faces/{detection_id}
GET /api/v1/sse/entities/{entity_id}/document-mentions/{document_mention_id}
GET /api/v1/sse/principals/{principal_id}/entities
GET /api/v1/sse/principals/{principal_id}/faces
GET /api/v1/sse/principals/{principal_id}/page-mentions
GET /api/v1/sse/principals/{principal_id}/document-mentions
GET /api/v1/sse/principals/{principal_id}/model-agents
GET /api/v1/sse/principals/{principal_id}/users
GET /api/v1/sse/principals/{principal_id}/sources
GET /api/v1/sse/principals/{principal_id}/entities/{entity_id}
GET /api/v1/sse/principals/{principal_id}/faces/{detection_id}
GET /api/v1/sse/principals/{principal_id}/page-mentions/{page_mention_id}
GET /api/v1/sse/principals/{principal_id}/document-mentions/{document_mention_id}
GET /api/v1/sse/principals/{principal_id}/model-agents/{model_agent_id}
GET /api/v1/sse/principals/{principal_id}/users/{user_id}
GET /api/v1/sse/principals/{principal_id}/sources/{source_id}
GET /api/v1/sse/sources/{source_id}/faces
GET /api/v1/sse/sources/{source_id}/page-mentions
GET /api/v1/sse/sources/{source_id}/document-mentions
GET /api/v1/sse/sources/{source_id}/faces/{detection_id}
GET /api/v1/sse/sources/{source_id}/page-mentions/{page_mention_id}
GET /api/v1/sse/sources/{source_id}/document-mentions/{document_mention_id}
```

There is intentionally no `/{topic_path:path}` fallback. A path not listed by the SSE router is not a valid subscription path.

Example:

```text
GET /api/v1/sse/entities/0194f5c6-...
```

The endpoint requires the browse dependency and therefore currently requires the `people-gator:browse` scope according to the active authentication implementation.

The response is an SSE stream with the `text/event-stream` media type. Each published `ServerSentEvent` is emitted by FastAPI's `EventSourceResponse` implementation.

A client can consume the stream in a browser with:

```javascript
const events = new EventSource(
  "/api/v1/sse/entities/0194f5c6-..."
);

events.addEventListener("entity_updated", (message) => {
  const entity = JSON.parse(message.data);
  console.log("Entity changed", entity);
});
```

The current route does not emit a synthetic connection event or heartbeat. The first response event is therefore the first event published after subscription.

## Topic Model

A topic is a tuple of path segments:

```python
type Topic = tuple[str | uuid.UUID | None, ...]
```

The HTTP route converts slash-separated path text into topic segments. Internally, producers may use strings, UUIDs, or `None` in a topic. UUIDs are normalized to their string representation for subscription lookup.

These topics represent different levels of observation:

```text
("entities",)
("entities", entity_id)
("entities", entity_id, "faces", face_id)
```

Topic segments are ordered and exact. There is no wildcard syntax and no pattern matching beyond ancestor propagation.

### Ancestor propagation

When an event is published to a topic, the broker sends it to subscribers of:

- the exact topic;
- every non-empty parent topic.

For example, publishing to:

```text
("entities", entity_id, "faces", face_id)
```

notifies subscribers of all of these topics:

```text
("entities", entity_id, "faces", face_id)
("entities", entity_id, "faces")
("entities", entity_id)
("entities",)
```

This lets a client monitor either one resource or a broader collection without requiring producers to know every parent subscriber. A consumer subscribed to `entities/{entity_id}` receives changes to the entity and its descendant resources that are published below that topic.

### Topics containing `None`

`LocalTopicBroker.publish()` skips a publication if any topic segment is `None`. This prevents an event from being sent to an ambiguous path such as:

```python
("entities", None, "faces", face_id)
```

The other explicitly supplied topics are still published by `publish_to_topics()`. This is useful when a relationship is optional: producers can provide all possible relationship topics and the broker ignores only invalid ones.

## Broker Interface

The transport contract is `TopicBroker`:

```python
class TopicBroker(Protocol):
    def subscribe(
        self, topic: Topic
    ) -> AbstractAsyncContextManager[AsyncIterator[ServerSentEvent]]: ...

    async def publish(
        self,
        topic: Topic,
        event: SseEventType,
        data: BaseModel,
        id: str | None = None,
        retry: int | None = None,
        comment: str | None = None,
    ) -> None: ...

    async def publish_to_topics(
        self,
        *topics: Topic,
        event: SseEventType,
        data: BaseModel,
    ) -> None: ...
```

The `event` and `data` arguments of `publish_to_topics()` are keyword-only. Topics are variadic so a producer can express all affected views directly:

```python
await broker.publish_to_topics(
    ("faces", face.detection_id),
    ("entities", face.entity_id, "faces", face.detection_id),
    ("sources", face.source_id, "faces", face.detection_id),
    event=SseEventType.FACE_UPDATED,
    data=face,
)
```

`publish_to_topics()` publishes to all supplied topics concurrently with `asyncio.gather()`. It does not deduplicate topics. If the same topic is supplied twice, its subscribers receive the event twice.

### Dependency injection

Routes receive the broker through the typed dependency:

```python
broker: BrokerDependency
```

`BrokerDependency` resolves `get_sse_broker()`. The module-level broker is currently a `LocalTopicBroker` instance:

```python
_sse_broker: TopicBroker = LocalTopicBroker()
```

This keeps route code independent of the concrete broker class. A future application setup can replace the dependency provider with a Redis-backed implementation that satisfies `TopicBroker`.

## Event Types

Event names are represented by `SseEventType`, a `StrEnum`. The enum values are the wire-level SSE event names.

| Enum member | Wire event name | Typical resource |
|---|---|---|
| `USER_CREATED` | `user_created` | User |
| `USER_UPDATED` | `user_updated` | User |
| `MODEL_AGENT_CREATED` | `model_agent_created` | Model agent |
| `MODEL_AGENT_UPDATED` | `model_agent_updated` | Model agent |
| `MODEL_AGENT_DELETED` | `model_agent_deleted` | Model agent |
| `ENTITY_CREATED` | `entity_created` | Entity |
| `ENTITY_UPDATED` | `entity_updated` | Entity |
| `ENTITY_DELETED` | `entity_deleted` | Entity |
| `DOCUMENT_MENTION_CREATED` | `document_mention_created` | Document mention |
| `DOCUMENT_MENTION_UPDATED` | `document_mention_updated` | Document mention |
| `PAGE_MENTION_CREATED` | `page_mention_created` | Page mention |
| `FACE_CREATED` | `face_created` | Face |
| `FACE_UPDATED` | `face_updated` | Face |
| `SOURCE_CREATED` | `source_created` | Source |
| `SOURCE_UPDATED` | `source_updated` | Source |
| `SOURCE_DELETED` | `source_deleted` | Source |

The event name is separate from the Pydantic payload type. Clients should use the SSE `event` field to choose a handler and parse `data` according to the event's resource schema.

## Payloads

### Create and update events

Create and update events carry the corresponding response model as `data`:

| Resource | Payload model |
|---|---|
| Entity | `EntityResponse` |
| Document mention | `DocumentMentionResponse` |
| Page mention | `PageMentionResponse` |
| Face | `FaceResponse` |
| Model agent | `ModelAgentResponse` |
| User | `UserResponse` |
| Source | `SourceResponse` |

The payload is passed to `ServerSentEvent` as a Pydantic model. FastAPI serializes it for the SSE response.

### Delete events

Single-resource delete events use:

```python
class DeletedResourceEvent(BaseModel):
    resource_id: uuid.UUID
```

The current single-delete payloads are:

- `EntityDeleted`: `DeletedResourceEvent`
- `ModelAgentDeleted`: `DeletedResourceEvent`
- `SourceDeleted`: `DeletedResourceEvent`

Bulk entity deletion currently publishes the operation summary as `EntityDeleteManyResponse` on the `("entities",)` collection topic. It does not publish one event per deleted entity because the bulk service returns a count rather than the deleted resource records.

## Current Topic and Event Matrix

The following table documents the mutation routes currently publishing SSE events. Every listed topic also receives the event through its own ancestor topics.

| Mutation | Event | Direct topics | Payload |
|---|---|---|---|
| Create entity | `ENTITY_CREATED` | `entities/{entity_id}`; `principals/{principal_id}/entities/{entity_id}` | `EntityResponse` |
| Batch create entities | `ENTITY_CREATED` | Same topics for each returned entity | `EntityResponse` per entity |
| Update entity | `ENTITY_UPDATED` | `entities/{entity_id}`; `principals/{principal_id}/entities/{entity_id}` | `EntityResponse` |
| Delete entity | `ENTITY_DELETED` | `entities/{entity_id}`; `principals/{principal_id}/entities/{entity_id}` | `DeletedResourceEvent` |
| Bulk delete entities | `ENTITY_DELETED` | `entities` | `EntityDeleteManyResponse` |
| Create page mention | `PAGE_MENTION_CREATED` | `page-mentions/{id}`; `document-mentions/{id}/page-mentions/{id}`; `sources/{id}/page-mentions/{id}`; `principals/{id}/page-mentions/{id}` | `PageMentionResponse` |
| Create document mention | `DOCUMENT_MENTION_CREATED` | `document-mentions/{id}`; `entities/{id}/document-mentions/{id}`; `sources/{id}/document-mentions/{id}`; `principals/{id}/document-mentions/{id}` | `DocumentMentionResponse` |
| Update document mention entity | `DOCUMENT_MENTION_UPDATED` | Same document mention, entity, source, and principal topics | `DocumentMentionResponse` |
| Create face | `FACE_CREATED` | `faces/{id}`; `entities/{id}/faces/{id}`; `principals/{id}/faces/{id}`; `sources/{id}/faces/{id}` | `FaceResponse` |
| Update face entity | `FACE_UPDATED` | Same face, entity, principal, and source topics | `FaceResponse` |
| Create model agent | `MODEL_AGENT_CREATED` | `principals/{id}`; `model-agents/{id}` | `ModelAgentResponse` |
| Update model agent | `MODEL_AGENT_UPDATED` | `principals/{id}`; `model-agents/{id}` | `ModelAgentResponse` |
| Delete model agent | `MODEL_AGENT_DELETED` | `principals/{id}`; `model-agents/{id}` | `DeletedResourceEvent` |
| Update user | `USER_UPDATED` | `principals/{id}`; `users/{id}` | `UserResponse` |
| Create source | `SOURCE_CREATED` | `sources/{id}` | `SourceResponse` |
| Delete source | `SOURCE_DELETED` | `sources/{id}` | `DeletedResourceEvent` |

The current route layer does not yet publish `USER_CREATED` or `SOURCE_UPDATED`; those enum values are reserved for future mutation routes or service-level producers.

## Consumer Lifecycle

A subscription is an asynchronous context manager:

```python
async with broker.subscribe(("entities", entity_id)) as events:
    async for event in events:
        handle(event)
```

The local broker performs these steps:

1. Create an `asyncio.Queue[ServerSentEvent]` for the consumer.
2. Register the queue under the normalized topic.
3. Yield an async iterator over the queue.
4. Remove the queue when the context exits.
5. Remove the topic entry when its final subscriber disconnects.

The SSE route uses this lifecycle directly. When the HTTP client disconnects, the async generator is closed and the subscription cleanup runs.

### Closing a topic

The broker can terminate all currently active subscribers of one exact topic:

```python
broker.close_topic(("entities", entity_id))
```

`close_topic()` places an internal close sentinel into each subscriber queue. The stream ends normally, and the subscription context removes each subscriber from the broker. Closure applies only to the exact topic; subscribers of ancestor topics are not closed. Closing a topic does not prevent a later client from subscribing to the same topic.

## Delivery Semantics

The local broker currently provides live, in-memory fan-out with these properties:

- **No persistence:** events are not written to a database, Redis, or a stream log.
- **No replay:** a client receives only events published after its subscription is registered.
- **No acknowledgement:** consumers do not acknowledge individual events.
- **No ordering guarantee across topics:** one call to `publish_to_topics()` publishes concurrently to all supplied topics. Each individual queue receives events in the order its `publish()` calls enqueue them.
- **Unbounded queues:** subscriber queues have no configured maximum size. A slow or abandoned consumer can retain events and memory until its subscription is cleaned up.
- **Best effort for disconnected clients:** events published after a client disconnects are not recoverable.
- **Process-local visibility:** subscribers and producers must be in the same Python process. Multiple API workers do not share subscriptions.
- **Transport errors propagate:** `publish_to_topics()` uses `asyncio.gather()` without `return_exceptions=True`; an exception from a broker publication is propagated to its caller.

These semantics are appropriate for the initial local interface, but they are not sufficient for durable cross-worker delivery or guaranteed event processing.

## Producer Guidelines

### Publish after persistence

A producer should publish only after the underlying mutation has succeeded and the response model contains the final persisted state:

```python
entity = await create_entity(session, payload, principal.principal_id)
await broker.publish_to_topics(
    ("entities", entity.entity_id),
    ("principals", entity.principal_id, "entities", entity.entity_id),
    event=SseEventType.ENTITY_CREATED,
    data=entity,
)
return entity
```

### Include every affected relationship

When a resource appears in multiple list views, publish the same event to each relevant relationship topic. For example, a face belongs to the global face collection and is also visible through an entity, principal, and source:

```python
await broker.publish_to_topics(
    ("faces", face.detection_id),
    ("entities", face.entity_id, "faces", face.detection_id),
    ("principals", face.principal_id, "faces", face.detection_id),
    ("sources", face.source_id, "faces", face.detection_id),
    event=SseEventType.FACE_UPDATED,
    data=face,
)
```

### Use typed payloads

Use a Pydantic response model for create and update events. Use `DeletedResourceEvent` or a dedicated Pydantic summary model for deletion events. Do not pass raw dictionaries or arbitrary objects to the broker.

### Handle optional relationships explicitly

If a relationship can be absent, pass the topic containing `None` only when convenient; the local broker skips that topic. Prefer constructing only valid topics when the producer can easily do so, because this makes behavior clearer for future broker implementations.

## Testing the Broker

A focused test should subscribe at both a leaf and an ancestor, publish once, and assert that both receive the same event:

```python
async with broker.subscribe(("entities",)) as collection_events:
    async with broker.subscribe(("entities", entity_id)) as resource_events:
        await broker.publish(
            ("entities", entity_id),
            event=SseEventType.ENTITY_UPDATED,
            data=entity,
        )
        assert await anext(collection_events) == await anext(resource_events)
```

Also test that:

- multiple consumers on one topic each receive the event;
- subscriptions are removed when their context exits;
- topics containing `None` do not receive events;
- `publish_to_topics()` publishes to every supplied relationship topic;
- deletion payloads expose `resource_id`;
- the SSE route returns an `EventSourceResponse` and streams `ServerSentEvent` values.

The focused broker tests are located at `tests/services/test_sse_service.py` and can be run with:

```bash
uv run pytest tests/services/test_sse_service.py
```

Strict type checking for the SSE service and routes can be run with:

```bash
uv run pyright \
  src/people_gator_api/services/sse \
  src/people_gator_api/routes/v1/entities.py \
  src/people_gator_api/routes/v1/annotations.py \
  src/people_gator_api/routes/v1/principals.py \
  src/people_gator_api/routes/v1/sources.py
```

## Future Distributed Broker

A Redis-backed implementation should implement `TopicBroker` rather than being referenced directly by routes. The likely responsibilities are:

- normalize topic keys consistently with `LocalTopicBroker`;
- map subscriptions to Redis Pub/Sub channels or Redis Streams;
- preserve ancestor propagation, either by publishing to each ancestor channel or by using a subscription index;
- define behavior for reconnects and `Last-Event-ID`;
- decide whether events are ephemeral Pub/Sub messages or durable Stream entries;
- bound or monitor consumer backlog;
- close Redis connections when the application lifespan ends;
- preserve the Pydantic-to-SSE serialization contract.

Redis Pub/Sub would preserve live fan-out but would lose events while a consumer is disconnected. Redis Streams would support replay and durable backlog, but would require explicit retention, cursor, and consumer-group policy. Neither should change the route-level `TopicBroker` contract unless the delivery semantics are intentionally changed.

## Source Locations

- Broker implementation: `src/people_gator_api/services/sse/service.py`
- SSE endpoint: `src/people_gator_api/routes/v1/sse.py`
- Public SSE exports: `src/people_gator_api/services/sse/__init__.py`
- Mutation event producers: `src/people_gator_api/routes/v1/entities.py`, `annotations.py`, `principals.py`, and `sources.py`
- Focused tests: `tests/services/test_sse_service.py`
