"""Seed synthetic preview data after running database migrations."""

import argparse
import asyncio
import logging

from people_gator_api.cli.database import check_database
from people_gator_api.seeding.fixtures import DOCUMENTS, PAGES
from people_gator_api.seeding.preview import seed_preview
from people_gator_api.services.database_service import close_db, get_database
from people_gator_api.services.filesystem_service import get_filesystem
from people_gator_api.settings import settings


async def seed_database() -> None:
    await check_database()
    try:
        async for database in get_database():
            result = await seed_preview(database, get_filesystem())
            print(result.model_dump_json(indent=2))
            base_url = settings.jwk.issuer.rstrip("/")
            for key, entity_id in result.entities.items():
                print(f"{key}: {base_url}/people/{entity_id}")
            for key, relative_url in result.filter_examples.items():
                print(f"{key}: {base_url}{relative_url}")
            for page in PAGES:
                document = next(item for item in DOCUMENTS if item.key == page.document)
                print(
                    f"{page.key}: {base_url}/libraries/{document.library}/documents/{document.document_id}/pages/{page.page_id}"
                )
    finally:
        await close_db()


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_database())


if __name__ == "__main__":
    main()
