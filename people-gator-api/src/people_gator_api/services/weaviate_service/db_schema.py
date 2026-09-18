"""Explicit Weaviate collection schema for canonical API persistence."""

import re

from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    ReferenceProperty,
    VectorDistances,
)

from people_gator_api.schemas.enums import AnnotationType, FaceEmbeddingModel

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

USER_COLLECTION = "User"
SOURCE_COLLECTION = "Source"
ENTITY_COLLECTION = "Entity"
FACE_COLLECTION = "Face"
TEXT_MENTION_COLLECTION = "TextMention"

# ---------------------------------------------------------------------------
# Named vector names
# ---------------------------------------------------------------------------

FACE_VECTOR_PREFIX = "face"
NAME_VECTOR_PREFIX = "name"
FULLTEXT_VECTOR_PREFIX = "fulltext"

MICROSOFT_HARRIER_OSS_V1_0_6B = "harrier-oss-v1-0.6b"
GAUNERNST_VIT_SMALL_PATCH8_GAP_112_COSFACE_MS1MV3 = (
    "vit_small_patch8_gap_112.cosface_ms1mv3"
)


def _graph_ql_safe_name(value: str) -> str:
    sanitized = re.sub(r"[^0-9A-Za-z_]", "_", value)
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized:
        raise ValueError(
            "Named vector identifier must not be empty after sanitization."
        )
    if sanitized[0].isdigit():
        sanitized = f"v_{sanitized}"
    return sanitized[:230]


DEFAULT_FACE_VECTOR = (
    FACE_VECTOR_PREFIX
    + "_"
    + _graph_ql_safe_name(GAUNERNST_VIT_SMALL_PATCH8_GAP_112_COSFACE_MS1MV3)
)
DEFAULT_NAME_VECTOR = (
    NAME_VECTOR_PREFIX + "_" + _graph_ql_safe_name(MICROSOFT_HARRIER_OSS_V1_0_6B)
)
DEFAULT_FULLTEXT_VECTOR = (
    FULLTEXT_VECTOR_PREFIX + "_" + _graph_ql_safe_name(MICROSOFT_HARRIER_OSS_V1_0_6B)
)

FACE_VECTOR_BY_MODEL: dict[FaceEmbeddingModel, str] = {
    FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3: (
        DEFAULT_FACE_VECTOR
    ),
}

ANNOTATION_COLLECTION_BY_TYPE: dict[AnnotationType, str] = {
    AnnotationType.face: FACE_COLLECTION,
    AnnotationType.entity: ENTITY_COLLECTION,
}


def _uuid_property(name: str, description: str) -> Property:
    return Property(
        name=name,
        data_type=DataType.UUID,
        description=description,
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    )


def _text_property(
    name: str,
    description: str,
    *,
    searchable: bool = True,
) -> Property:
    return Property(
        name=name,
        data_type=DataType.TEXT,
        description=description,
        index_filterable=True,
        index_searchable=searchable,
        skip_vectorization=True,
    )


def _text_array_property(
    name: str,
    description: str,
    *,
    searchable: bool = True,
) -> Property:
    return Property(
        name=name,
        data_type=DataType.TEXT_ARRAY,
        description=description,
        index_filterable=True,
        index_searchable=searchable,
        skip_vectorization=True,
    )


def _bool_property(name: str, description: str) -> Property:
    return Property(
        name=name,
        data_type=DataType.BOOL,
        description=description,
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    )


def _int_property(name: str, description: str) -> Property:
    return Property(
        name=name,
        data_type=DataType.INT,
        description=description,
        index_filterable=True,
        index_searchable=False,
        index_range_filters=True,
        skip_vectorization=True,
    )


def _number_property(name: str, description: str) -> Property:
    return Property(
        name=name,
        data_type=DataType.NUMBER,
        description=description,
        index_filterable=True,
        index_searchable=False,
        index_range_filters=True,
        skip_vectorization=True,
    )


def _object_property(
    name: str,
    description: str,
    *,
    nested_properties: list[Property] | None = None,
) -> Property:
    return Property(
        name=name,
        data_type=DataType.OBJECT,
        description=description,
        index_filterable=True,
        index_searchable=False,
        nested_properties=nested_properties,
        skip_vectorization=True,
    )


def _object_array_property(
    name: str,
    description: str,
    *,
    nested_properties: list[Property],
    index_filterable: bool = True,
    skip_vectorization: bool = True,
) -> Property:
    return Property(
        name=name,
        data_type=DataType.OBJECT_ARRAY,
        description=description,
        index_filterable=index_filterable,
        nested_properties=nested_properties,
        skip_vectorization=skip_vectorization,
    )


def _named_vector(name: str) -> object:
    return Configure.Vectors.self_provided(
        name=name,
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        ),
    )


def default_name_plus_fulltext_vector_config() -> list[object]:
    return [
        _named_vector(DEFAULT_NAME_VECTOR),
        _named_vector(DEFAULT_FULLTEXT_VECTOR),
    ]


def default_fulltext_vector_config() -> list[object]:
    return [_named_vector(DEFAULT_FULLTEXT_VECTOR)]


def default_name_vector_config() -> list[object]:
    return [_named_vector(DEFAULT_NAME_VECTOR)]


def default_face_vector_config() -> list[object]:
    return [_named_vector(DEFAULT_FACE_VECTOR)]


BOUNDING_BOX_PROPERTIES = [
    _int_property("x", "Bounding box left coordinate."),
    _int_property("y", "Bounding box top coordinate."),
    _int_property("width", "Bounding box width."),
    _int_property("height", "Bounding box height."),
]

FACE_KEYPOINT_PROPERTIES = [
    _text_property("type", "Keypoint type label.", searchable=False),
    _number_property("x", "Keypoint horizontal coordinate."),
    _number_property("y", "Keypoint vertical coordinate."),
]

USER_PROPERTIES: list[Property] = [
    _text_property("display_name", "Human-readable display name."),
    _bool_property("is_active", "Whether the user is active."),
    _text_property("external_subject", "OIDC subject."),
    _text_property("external_issuer", "OIDC issuer."),
    _text_property("email", "Email address."),
]

SOURCE_PROPERTIES: list[Property] = [
    _text_property("source_type", "Source kind.", searchable=False),
    _text_property("uri", "Source URI."),
    _text_property("library", "Archive library identifier.", searchable=False),
    _uuid_property("document", "Archive document identifier."),
    _uuid_property("page", "Archive page identifier."),
]

ENTITY_PROPERTIES: list[Property] = [
    _text_property("entity_type", "Entity type discriminator.", searchable=False),
    _text_property("name", "Entity-level aggregated name value."),
    _text_property("description", "Entity-level aggregated description value."),
    _text_property(
        "short_description", "Entity-level aggregated short description value."
    ),
    _text_array_property(
        "aliases",
        "Entity-level aggregated alias values.",
        searchable=True,
    ),
    _text_property("wikidata_id", "Entity-level aggregated Wikidata ID."),
    _text_property("nlcr_authority_id", "Entity-level aggregated NLCR authority ID."),
]

FACE_PROPERTIES: list[Property] = [
    _object_property(
        "bounding_box",
        "Bounding box coordinates.",
        nested_properties=BOUNDING_BOX_PROPERTIES,
    ),
    _object_array_property(
        "keypoints",
        "Ordered face keypoints.",
        nested_properties=FACE_KEYPOINT_PROPERTIES,
    ),
    _number_property("confidence", "Detection confidence."),
]

TEXT_MENTION_PROPERTIES: list[Property] = [
    _text_property("name", "Entity name as it appears in the source."),
    _text_property("context", "Optional surrounding text for the mention."),
]

USER_REFERENCES: list[ReferenceProperty] = []
SOURCE_REFERENCES: list[ReferenceProperty] = []
ENTITY_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="user",
        target_collection=USER_COLLECTION,
        description="User that created the entity.",
    ),
    ReferenceProperty(
        name="mentioned_in",
        target_collection=SOURCE_COLLECTION,
        description="Document or page sources in which the entity is mentioned.",
    ),
]
FACE_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity associated with the face detection.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the face detection.",
    ),
    ReferenceProperty(
        name="user",
        target_collection=USER_COLLECTION,
        description="User that performed the detection.",
    ),
]

TEXT_MENTION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity identified by this text mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing this text mention.",
    ),
]

type CollectionVectorConfig = list[object] | None
type CollectionSpec = tuple[
    list[Property], list[ReferenceProperty], CollectionVectorConfig
]

ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    FACE_COLLECTION: (
        FACE_PROPERTIES,
        FACE_REFERENCES,
        default_face_vector_config(),
    ),
    TEXT_MENTION_COLLECTION: (
        TEXT_MENTION_PROPERTIES,
        TEXT_MENTION_REFERENCES,
        None,
    ),
}

NON_ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    USER_COLLECTION: (
        USER_PROPERTIES,
        USER_REFERENCES,
        None,
    ),
    SOURCE_COLLECTION: (
        SOURCE_PROPERTIES,
        SOURCE_REFERENCES,
        None,
    ),
    ENTITY_COLLECTION: (
        ENTITY_PROPERTIES,
        ENTITY_REFERENCES,
        default_name_plus_fulltext_vector_config(),
    ),
}

ALL_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    **NON_ANNOTATION_COLLECTION_SPECS,
    **ANNOTATION_COLLECTION_SPECS,
}


def collection_for_annotation_type(annotation_type: AnnotationType) -> str:
    return ANNOTATION_COLLECTION_BY_TYPE[annotation_type]
