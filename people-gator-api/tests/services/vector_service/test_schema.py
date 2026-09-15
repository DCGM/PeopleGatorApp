import re

from people_gator_api.services.weaviate_service import db_schema


def test_source_schema_stores_archive_identity_at_top_level() -> None:
    property_names = {property_.name for property_ in db_schema.SOURCE_PROPERTIES}

    assert "metadata" not in property_names
    assert {"source_type", "uri", "library", "document", "page"} <= property_names


def test_default_named_vectors_are_graphql_safe() -> None:
    graph_ql_name_pattern = re.compile(r"^[_A-Za-z][_0-9A-Za-z]{0,229}$")

    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FACE_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_NAME_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FULLTEXT_VECTOR)
