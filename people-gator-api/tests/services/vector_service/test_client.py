import pytest
from weaviate.classes.config import ReferenceProperty

from people_gator_api.services.weaviate_service import client
from people_gator_api.services.weaviate_service import db_schema


def test_ordered_collection_specs_respect_reference_dependencies() -> None:
    ordered_collection_names = [
        collection_name
        for collection_name, _ in client.ordered_collection_specs(db_schema.ALL_COLLECTION_SPECS)
    ]

    assert ordered_collection_names.index(db_schema.PRINCIPAL_COLLECTION) < ordered_collection_names.index(
        db_schema.ENTITY_COLLECTION
    )
    assert ordered_collection_names.index(db_schema.DOCUMENT_MENTION_COLLECTION) < ordered_collection_names.index(
        db_schema.PAGE_MENTION_COLLECTION
    )
    assert ordered_collection_names.index(db_schema.PAGE_MENTION_COLLECTION) < ordered_collection_names.index(
        db_schema.SPAN_COLLECTION
    )


def test_ordered_collection_specs_reject_cycles() -> None:
    cyclic_specs: dict[str, db_schema.CollectionSpec] = {
        "Alpha": (
            [],
            [
                ReferenceProperty(
                    name="beta",
                    target_collection="Beta",
                    description="Depends on Beta.",
                )
            ],
            None,
        ),
        "Beta": (
            [],
            [
                ReferenceProperty(
                    name="alpha",
                    target_collection="Alpha",
                    description="Depends on Alpha.",
                )
            ],
            None,
        ),
    }

    with pytest.raises(ValueError, match="unresolved reference dependencies"):
        client.ordered_collection_specs(cyclic_specs)
