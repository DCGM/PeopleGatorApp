from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from people_gator_api.models import Source
from people_gator_api.persistence.postgres.utils import source_filters
from people_gator_api.schemas.sources import PageListFilter


def _sql(filter_: PageListFilter) -> str:
    statement = select(Source).where(*source_filters(filter_.to_generic()))
    return str(statement.compile(dialect=postgresql.dialect()))


def test_page_presence_filters_use_correlated_annotation_existence_checks() -> None:
    sql = _sql(
        PageListFilter(
            has_mentions=True,
            has_faces=True,
            has_entities=True,
        )
    )

    assert sql.count("pg_demo_text_mentions.source_id = pg_demo_sources.id") == 2
    assert sql.count("pg_demo_faces.id = pg_demo_image_occurrences.id") == 2
    assert "pg_demo_text_mentions.entity_id IS NOT NULL" in sql
    assert "pg_demo_image_occurrences.entity_id IS NOT NULL" in sql


def test_false_page_presence_filters_negate_existence_checks() -> None:
    sql = _sql(
        PageListFilter(
            has_mentions=False,
            has_faces=False,
            has_entities=False,
        )
    )

    assert sql.count("NOT (EXISTS") == 2
    assert "NOT ((EXISTS" in sql
