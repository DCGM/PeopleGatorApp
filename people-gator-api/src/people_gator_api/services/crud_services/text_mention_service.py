"""CRUD service for entity-name mentions in text sources."""

import logging
import uuid
from collections.abc import AsyncGenerator

from weaviate import WeaviateAsyncClient
from weaviate.collections.classes.filters import FilterReturn

from people_gator_api.schemas.text_mentions import (
    TextMentionCreateRequest,
    TextMentionListResponse,
    TextMentionResponse,
)
from people_gator_api.services.weaviate_service.db_schema import (
    TEXT_MENTION_COLLECTION,
)
from people_gator_api.services.weaviate_service.utils import (
    combine_filters,
    empty_reference_queries,
    fetch_collection_object,
    fetch_collection_page_with_total_count,
    parse_text_mention,
    reference_id_filter,
)
from people_gator_api.utils.opentelemetry import trace
from people_gator_api.utils.uuid_utils import new_uuid6


logger = logging.getLogger(__name__)


@trace()
async def create_text_mention(
    client: WeaviateAsyncClient,
    payload: TextMentionCreateRequest,
) -> TextMentionResponse:
    mention_id = new_uuid6()
    await client.collections.get(TEXT_MENTION_COLLECTION).data.insert(
        uuid=mention_id,
        properties={
            "name": payload.name,
            "context": payload.context,
        },
        references={
            "entity": payload.entity_id,
            "source": payload.source_id,
        },
    )
    logger.info(
        "Created text mention",
        extra={
            "mention_id": mention_id,
            "entity_id": payload.entity_id,
            "source_id": payload.source_id,
        },
    )
    return TextMentionResponse(
        mention_id=mention_id,
        name=payload.name,
        context=payload.context,
        entity_id=payload.entity_id,
        source_id=payload.source_id,
    )


@trace()
async def create_text_mention_batch(
    client: WeaviateAsyncClient,
    payloads: AsyncGenerator[TextMentionCreateRequest, None],
) -> list[TextMentionResponse]:
    """Insert text mentions as one streamed Weaviate batch."""
    collection = client.collections.use(TEXT_MENTION_COLLECTION)
    responses: list[TextMentionResponse] = []
    async with collection.batch.stream() as batch:
        async for payload in payloads:
            mention_id = new_uuid6()
            await batch.add_object(
                uuid=mention_id,
                properties={
                    "name": payload.name,
                    "context": payload.context,
                },
                references={
                    "entity": payload.entity_id,
                    "source": payload.source_id,
                },
            )
            responses.append(
                TextMentionResponse(
                    mention_id=mention_id,
                    name=payload.name,
                    context=payload.context,
                    entity_id=payload.entity_id,
                    source_id=payload.source_id,
                )
            )
    logger.info(
        "Created text mention batch",
        extra={"count": len(responses)},
    )
    return responses


@trace()
async def get_text_mention(
    client: WeaviateAsyncClient,
    mention_id: uuid.UUID,
) -> TextMentionResponse | None:
    response = await fetch_collection_object(
        client,
        TEXT_MENTION_COLLECTION,
        mention_id,
        reference_names=["entity", "source"],
    )
    if response is None:
        return None
    return parse_text_mention(
        response.properties,
        response.references,
        response.uuid,
    )


@trace()
async def list_text_mentions(
    client: WeaviateAsyncClient,
    *,
    source_id: uuid.UUID | None,
    entity_id: uuid.UUID | None,
    after_id: uuid.UUID | None,
    limit: int,
) -> TextMentionListResponse:
    filters: list[FilterReturn] = []
    if source_id is not None:
        filters.append(reference_id_filter(link_on="source", reference_id=source_id))
    if entity_id is not None:
        filters.append(reference_id_filter(link_on="entity", reference_id=entity_id))

    objects, total_count = await fetch_collection_page_with_total_count(
        client,
        TEXT_MENTION_COLLECTION,
        filters=combine_filters(filters),
        limit=limit,
        return_references=empty_reference_queries(["entity", "source"]),
        after_id=after_id,
    )
    items = sorted(
        [
            parse_text_mention(
                item.properties,
                item.references,
                item.uuid,
            )
            for item in objects
        ],
        key=lambda item: item.mention_id,
    )
    return TextMentionListResponse(
        items=items,
        total_count=total_count,
        limit=limit,
        after_id=(
            items[-1].mention_id if len(items) == limit and items else None
        ),
    )


@trace()
async def reassign_text_mention_entity(
    client: WeaviateAsyncClient,
    mention_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> TextMentionResponse | None:
    mention = await get_text_mention(client, mention_id)
    if mention is None:
        return None

    await client.collections.get(TEXT_MENTION_COLLECTION).data.reference_replace(
        from_uuid=mention_id,
        from_property="entity",
        to=entity_id,
    )
    logger.info(
        "Reassigned text mention entity",
        extra={"mention_id": mention_id, "entity_id": entity_id},
    )
    return mention.model_copy(update={"entity_id": entity_id})
