import uuid

import pytest
from sqlalchemy.dialects import postgresql

from people_gator_api.services.postgres_demo.queries import (
    DocumentRef,
    entity_alias_search_excluding_document_statement,
    entity_description_vector_search_statement,
    face_vector_search_statement,
)


def _sql(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_alias_search_combines_fts_trigrams_and_exact_document_exclusion() -> None:
    document_id = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    sql = _sql(
        entity_alias_search_excluding_document_statement(
            "Masaryk",
            DocumentRef(library="mzk", document_id=document_id),
            minimum_similarity=0.2,
            limit=7,
        )
    )

    assert "similarity(" in sql
    assert "websearch_to_tsquery" in sql
    assert "@@" in sql
    assert "NOT (EXISTS" in sql
    assert "pg_demo_faces" in sql
    assert "pg_demo_pages" in sql
    assert "pg_demo_documents" in sql
    assert "'mzk'" in sql
    assert str(document_id) in sql
    assert "row_number() OVER (PARTITION BY" in sql
    assert "LIMIT 7" in sql


def test_entity_vector_search_is_scoped_by_model_field_and_dimension() -> None:
    sql = _sql(
        entity_description_vector_search_statement(
            [0.1, 0.2, 0.3],
            model="demo-text-model",
            field="short_description",
            limit=3,
        )
    )

    assert "<=>" in sql
    assert "CAST(pg_demo_entity_embeddings.embedding AS VECTOR(3))" in sql
    assert "'demo-text-model'" in sql
    assert "'short_description'" in sql
    assert "dimensions = 3" in sql


def test_face_vector_search_only_returns_face_subclass_rows() -> None:
    sql = _sql(face_vector_search_statement([0.1, 0.2], model="face-v1"))

    assert "pg_demo_faces" in sql
    assert "pg_demo_image_occurrences" in sql
    assert "pg_demo_image_occurrence_embeddings" in sql
    assert "CAST(pg_demo_image_occurrence_embeddings.embedding AS VECTOR(2))" in sql


@pytest.mark.parametrize("query", ["", "   "])
def test_alias_search_rejects_empty_queries(query: str) -> None:
    with pytest.raises(ValueError, match="query"):
        entity_alias_search_excluding_document_statement(
            query,
            DocumentRef(library="mzk", document_id=uuid.uuid4()),
        )
