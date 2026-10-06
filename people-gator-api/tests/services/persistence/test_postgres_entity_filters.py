import uuid

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from people_gator_api.persistence.postgres.models import Entity
from people_gator_api.persistence.postgres.utils import entity_filters as _entity_filters
from people_gator_api.schemas.entities import EntityListFilter
from people_gator_api.schemas.enums import EntityType


def test_source_filter_resolves_linked_ids_before_querying_entities() -> None:
    source_id = uuid.uuid4()
    filters = _entity_filters(EntityListFilter(source_id=[source_id]))

    statement = select(Entity).where(*filters).order_by(Entity.id).limit(4)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "pg_demo_entities.id IN" in sql
    assert "pg_demo_image_occurrences.source_id IN" in sql
    assert "pg_demo_text_mentions.source_id IN" in sql
    assert "UNION ALL" in sql
    assert "EXISTS" not in sql
    assert list(compiled.params.values()).count([source_id]) == 2


def test_source_filter_remains_anded_with_other_entity_filters() -> None:
    filters = _entity_filters(
        EntityListFilter(
            source_id=[uuid.uuid4()],
            entity_type=[EntityType.person],
        )
    )

    statement = select(Entity).where(*filters)
    sql = str(statement.compile(dialect=postgresql.dialect()))

    assert "pg_demo_entities.kind IN" in sql
    assert "pg_demo_entities.id IN" in sql
    assert "UNION ALL" in sql
