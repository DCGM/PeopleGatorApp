import pytest
from fastapi.sse import ServerSentEvent
from pydantic import BaseModel

from people_gator_api.services.sse import LocalTopicBroker, SseEventType, Topic


class EventData(BaseModel):
    operation: str


@pytest.mark.asyncio
async def test_leaf_events_reach_leaf_and_ancestor_consumers() -> None:
    broker = LocalTopicBroker()
    collection: Topic = ("entities",)
    resource: Topic = ("entities", "123")
    event_data = EventData(operation="modified")

    async with broker.subscribe(collection) as collection_events:
        async with broker.subscribe(resource) as resource_events:
            await broker.publish(resource, SseEventType.ENTITY_UPDATED, event_data)
            collection_event = await anext(collection_events)
            resource_event = await anext(resource_events)

    assert isinstance(collection_event, ServerSentEvent)
    assert isinstance(resource_event, ServerSentEvent)
    assert collection_event.event == SseEventType.ENTITY_UPDATED
    assert resource_event.event == SseEventType.ENTITY_UPDATED
    assert collection_event.data == event_data
    assert resource_event.data == event_data


@pytest.mark.asyncio
async def test_closing_subscription_removes_consumer() -> None:
    broker = LocalTopicBroker()
    topic: Topic = ("entities",)

    async with broker.subscribe(topic):
        assert broker.subscriber_count(topic) == 1

    assert broker.subscriber_count(topic) == 0


@pytest.mark.asyncio
async def test_closing_topic_terminates_active_stream() -> None:
    broker = LocalTopicBroker()
    topic: Topic = ("entities", "123")

    async with broker.subscribe(topic) as events:
        broker.close_topic(topic)
        with pytest.raises(StopAsyncIteration):
            await anext(events)

    assert broker.subscriber_count(topic) == 0