import re

from people_gator_api.services.weaviate_service import db_schema


def test_source_schema_stores_archive_identity_at_top_level() -> None:
    property_names = {property_.name for property_ in db_schema.SOURCE_PROPERTIES}

    assert "metadata" not in property_names
    assert {"source_type", "uri", "library", "document", "page"} <= property_names


def test_entity_schema_has_no_direct_source_reference() -> None:
    reference_names = {
        reference.name for reference in db_schema.ENTITY_REFERENCES
    }

    assert reference_names == {"user"}


def test_text_mention_schema_links_to_entity_and_source() -> None:
    property_names = {
        property_.name for property_ in db_schema.TEXT_MENTION_PROPERTIES
    }
    references = {
        reference.name: reference
        for reference in db_schema.TEXT_MENTION_REFERENCES
    }

    assert property_names == {"name", "context"}
    assert references["entity"].target_collection == db_schema.ENTITY_COLLECTION
    assert references["source"].target_collection == db_schema.SOURCE_COLLECTION
    assert db_schema.TEXT_MENTION_COLLECTION in db_schema.ALL_COLLECTION_SPECS


def test_default_named_vectors_are_graphql_safe() -> None:
    graph_ql_name_pattern = re.compile(r"^[_A-Za-z][_0-9A-Za-z]{0,229}$")

    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FACE_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_NAME_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FULLTEXT_VECTOR)


def test_user_schema_has_no_polymorphic_or_agent_fields() -> None:
    property_names = {property_.name for property_ in db_schema.USER_PROPERTIES}

    assert property_names == {
        "display_name",
        "is_active",
        "external_subject",
        "external_issuer",
        "email",
    }
    assert db_schema.USER_COLLECTION == "User"
    assert db_schema.ENTITY_REFERENCES[0].name == "user"
    assert db_schema.FACE_REFERENCES[-1].name == "user"
