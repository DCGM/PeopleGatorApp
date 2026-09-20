from sqlalchemy.dialects import postgresql

from people_gator_api.services.postgres_demo.models import (
    EntityEmbedding,
    Face,
    ImageOccurrence,
    Source,
    TextMention,
)


def test_required_and_optional_links_match_the_domain_model() -> None:
    assert not TextMention.__table__.c.source_id.nullable
    assert TextMention.__table__.c.entity_id.nullable
    assert not ImageOccurrence.__table__.c.source_id.nullable
    assert ImageOccurrence.__table__.c.entity_id.nullable


def test_joined_inheritance_is_configured() -> None:
    assert Face.__mapper__.inherits is ImageOccurrence.__mapper__
    assert Source.__mapper__.polymorphic_on is Source.__table__.c.source_type


def test_embeddings_use_unbounded_pgvector_for_per_model_dimensions() -> None:
    compiled_type = EntityEmbedding.__table__.c.embedding.type.compile(
        dialect=postgresql.dialect()
    )
    assert compiled_type == "VECTOR"
