import asyncio

import uvicorn

from people_gator_api.db import init_db as init_db_tables
from people_gator_api.settings import settings


def server() -> None:
    uvicorn.run(
        "people_gator_api.app:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
    )


def init_db() -> None:
    asyncio.run(init_db_tables())


if __name__ == "__main__":
    server()
