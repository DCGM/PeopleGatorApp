import pytest
from pydantic import BaseModel

from people_gator_api.services.sse import LocalTopicBroker, SseEvent, SseEventType, Topic


class EventData(BaseModel):
    operation: str


@pytest.mark.asyncio
async def test_leaf_events_reach_leaf_and_ancestor_consumers() -> None:
    broker = LocalTopicBroker(_max_notification_depth=2)
    collection: Topic = ("entities",)
    resource: Topic = ("entities", "123")
    event_data = EventData(operation="modified")

    async with broker.subscribe(SseEvent, collection) as collection_events:
        async with broker.subscribe(SseEvent, resource) as resource_events:
            await broker.publish_single(resource, SseEventType.ENTITY_UPDATED, event_data)
            collection_event = await anext(collection_events)
            resource_event = await anext(resource_events)

    assert isinstance(collection_event, SseEvent)
    assert isinstance(resource_event, SseEvent)
    assert collection_event.event == SseEventType.ENTITY_UPDATED
    assert resource_event.event == SseEventType.ENTITY_UPDATED
    assert EventData.model_validate(collection_event.data) == event_data
    assert EventData.model_validate(resource_event.data) == event_data


@pytest.mark.asyncio
async def test_closing_subscription_removes_consumer() -> None:
    broker = LocalTopicBroker()
    topic: Topic = ("entities",)

    async with broker.subscribe(SseEvent, topic):
        assert broker.subscriber_count(topic) == 1

    assert broker.subscriber_count(topic) == 0


@pytest.mark.asyncio
async def test_closing_topic_terminates_active_stream() -> None:
    broker = LocalTopicBroker()
    topic: Topic = ("entities", "123")

    async with broker.subscribe(SseEvent, topic) as events:
        broker.close_topic(topic)
        with pytest.raises(StopAsyncIteration):
            await anext(events)

    assert broker.subscriber_count(topic) == 0
