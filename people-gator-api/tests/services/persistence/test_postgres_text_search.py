from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from people_gator_api.persistence.postgres import PostgresEntityRepository
from people_gator_api.schemas.search import QueryBase, SearchEntitiesRequest


@pytest.mark.asyncio
async def test_entity_text_scores_use_bounded_index_backed_candidates() -> None:
    rows = Mock()
    rows.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = rows
    repository = PostgresEntityRepository(session)

    scores = await repository._text_scores(  # pyright: ignore[reportPrivateUsage]
        SearchEntitiesRequest(query=QueryBase(text=["Ada Lovelace"]), limit=10),
        [],
    )

    assert scores == {}
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "entity_text_candidates" in sql
    assert sql.count("name_normalized %%") == 2
    assert sql.count("word_similarity") >= 4
    assert "pg_demo_aliases" in sql
    assert "pg_demo_entities.id IN" in sql
    assert "description" not in sql
    assert list(compiled.params.values()).count(200) == 2
