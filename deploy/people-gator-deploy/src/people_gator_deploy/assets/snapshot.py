#!/usr/bin/env python3
"""Private staging database validator; storage and media are managed externally."""
from __future__ import annotations

import asyncio
import json
import re
import sys


async def connect():
    import asyncpg
    import people_gator_api.schemas  # initialize schema/settings imports in application order
    from people_gator_api.settings import settings
    config = settings.persistence.postgres
    if not re.fullmatch(r"staging_[a-f0-9]{16}", config.database):
        raise ValueError("Preparation requires an isolated staging generation database")
    return await asyncpg.connect(host=config.host, port=config.port, user=config.user,
                                 password=config.password, database=config.database)


async def validate_data(connection):
    invalid = await connection.fetchval("""SELECT count(*) FROM pg_demo_face_embeddings e
        JOIN pg_demo_face_models m ON m.stub=e.model_id WHERE vector_dims(e.embedding)<>m.embedding_dim""")
    if invalid:
        raise ValueError("Embedding/model dimension mismatch")
    # Execute a representative real vector query and a linked evidence join.
    await connection.fetch("""SELECT e.face_id FROM pg_demo_face_embeddings e
        JOIN pg_demo_faces f ON f.id=e.face_id JOIN pg_demo_image_occurrences o ON o.id=f.id
        JOIN pg_demo_sources s ON s.id=o.source_id
        ORDER BY e.embedding <=> e.embedding LIMIT 1""")
    await connection.fetch("""SELECT t.id FROM pg_demo_text_mentions t
        JOIN pg_demo_entities e ON e.id=t.entity_id JOIN pg_demo_sources s ON s.id=t.source_id LIMIT 1""")


async def main():
    connection = await connect()
    try:
        revision = await connection.fetchval("SELECT version_num FROM alembic_version")
        if not isinstance(revision, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", revision):
            raise ValueError("Missing/invalid source migration history")
        await validate_data(connection)
        print(json.dumps({"source_schema_revision": revision, "data_mode": "original"}))
    finally:
        await connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print(f"Private staging database validation failed ({type(error).__name__})", file=sys.stderr)
        sys.exit(1)
