from collections.abc import (
    AsyncGenerator,
)

from weaviate import (
    WeaviateAsyncClient,
)

from people_gator_api.services.vector_service.client import (
    close_weaviate,
    get_weaviate_client,
    init_weaviate,
)


async def get_session() -> AsyncGenerator[WeaviateAsyncClient, None]:
    yield get_weaviate_client()


async def init_db() -> None:
    await init_weaviate()
    await close_weaviate()
