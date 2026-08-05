from collections.abc import AsyncGenerator
from fastapi import Depends
from typing import Annotated

from weaviate import WeaviateAsyncClient

from people_gator_api.services.weaviate_service.client import (
    close_weaviate,
    get_weaviate_client,
    init_weaviate,
)


async def get_session() -> AsyncGenerator[WeaviateAsyncClient, None]:
    yield get_weaviate_client()

type WeaviateSessionDependency = Annotated[WeaviateAsyncClient, Depends(get_session)]

async def init_db() -> None:
    await init_weaviate()
    await close_weaviate()
