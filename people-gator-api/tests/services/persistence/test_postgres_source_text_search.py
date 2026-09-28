import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from people_gator_api.models import Document, Page
from people_gator_api.persistence.postgres import PostgresSourceRepository
from people_gator_api.schemas.search import QueryBase, SearchPagesRequest
from people_gator_api.schemas.sources import DocumentListFilter, PageListFilter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model", "rolls_up_pages"),
    [(Page, False), (Document, True)],
)
async def test_source_entity_links_use_bounded_mention_and_face_candidates(
    model: type[Page] | type[Document], rolls_up_pages: bool
) -> None:
    rows = Mock()
    rows.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = rows
    repository = PostgresSourceRepository(session)

    await repository._entity_source_scores(  # pyright: ignore[reportPrivateUsage]
        model, [(uuid.uuid4(), 0.8)], []
    )

    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "matched_entity_scores" in sql
    assert "pg_demo_text_mentions.entity_id" in sql
    assert "pg_demo_faces.id = pg_demo_image_occurrences.id" in sql
    assert "max(entity_source_links.score)" in sql
    assert 200 in compiled.params.values()
    assert (
        "pg_demo_documents.document_id = pg_demo_pages.document_id" in sql
    ) is rolls_up_pages


@pytest.mark.asyncio
async def test_source_text_scores_reuse_bounded_alias_matches() -> None:
    source_id = uuid.uuid4()
    entity_id = uuid.uuid4()
    direct_rows = Mock()
    direct_rows.all.return_value = []
    entity_rows = Mock()
    entity_rows.all.return_value = [(entity_id, 0.75)]
    session = AsyncMock()
    session.scalars.return_value = direct_rows
    session.execute.return_value = entity_rows
    repository = PostgresSourceRepository(session)
    repository._entity_source_scores = AsyncMock(  # type: ignore[method-assign]
        return_value=[(source_id, 0.75)]
    )

    scores = await repository._source_text_scores(  # pyright: ignore[reportPrivateUsage]
        Page,
        SearchPagesRequest(query=QueryBase(text=["Ada"]), limit=10),
        [],
    )

    assert scores == {source_id: 0.75}
    entity_sql = str(
        session.execute.await_args.args[0].compile(dialect=postgresql.dialect())
    )
    assert "entity_text_candidates" in entity_sql
    assert "pg_demo_aliases.name_normalized" in entity_sql
    assert "pg_demo_entities.id IN" in entity_sql


@pytest.mark.parametrize(
    ("model", "filter_", "other_table"),
    [
        (Page, PageListFilter(library=["mzk"]), "pg_demo_documents"),
        (Document, DocumentListFilter(library=["mzk"]), "pg_demo_pages"),
    ],
)
def test_source_search_filters_do_not_cross_join_other_source_type(
    model: type[Page] | type[Document],
    filter_: PageListFilter | DocumentListFilter,
    other_table: str,
) -> None:
    filters = PostgresSourceRepository._search_filters(  # pyright: ignore[reportPrivateUsage]
        model, filter_.to_generic()
    )
    sql = str(select(model.id).where(*filters).compile(dialect=postgresql.dialect()))

    assert other_table not in sql
    assert f"{model.__tablename__}.library IN" in sql
