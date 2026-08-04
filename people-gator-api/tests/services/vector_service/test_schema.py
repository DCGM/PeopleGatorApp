import re

from people_gator_api.services.weaviate_service import db_schema


def test_source_metadata_schema_declares_nested_properties() -> None:
    metadata_property = next(
        property_
        for property_ in db_schema.SOURCE_PROPERTIES
        if property_.name == "metadata"
    )
    metadata_payload = metadata_property.model_dump_json(by_alias=True)

    assert '"nested_properties"' in metadata_payload
    for nested_property_name in (
        "document",
        "entity_id",
        "kramerius_url",
        "library",
        "nlcr_id",
        "page",
        "wikidata_url",
        "wikimedia_url",
    ):
        assert f'"name":"{nested_property_name}"' in metadata_payload


def test_default_named_vectors_are_graphql_safe() -> None:
    graph_ql_name_pattern = re.compile(r"^[_A-Za-z][_0-9A-Za-z]{0,229}$")

    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FACE_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_NAME_VECTOR)
    assert graph_ql_name_pattern.fullmatch(db_schema.DEFAULT_FULLTEXT_VECTOR)
