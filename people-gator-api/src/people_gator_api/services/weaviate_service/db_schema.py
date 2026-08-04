"""Explicit Weaviate collection schema for canonical API persistence."""

import re

from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    ReferenceProperty,
    VectorDistances,
)

from people_gator_api.schemas.enums import (
    AnnotationType,
)

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

PRINCIPAL_COLLECTION = "Principal"
SOURCE_COLLECTION = "Source"
ENTITY_COLLECTION = "Entity"
PAGE_MENTION_COLLECTION = "PageMention"
DOCUMENT_MENTION_COLLECTION = "DocumentMention"
FACE_COLLECTION = "Face"

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
        raise ValueError("Named vector identifier must not be empty after sanitization.")
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

ANNOTATION_COLLECTION_BY_TYPE: dict[AnnotationType, str] = {
    AnnotationType.document_mention: DOCUMENT_MENTION_COLLECTION,
    AnnotationType.page_mention: PAGE_MENTION_COLLECTION,
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
    index_searchable: bool = False,
    skip_vectorization: bool = True,
) -> Property:
    return Property(
        name=name,
        data_type=DataType.OBJECT_ARRAY,
        description=description,
        index_filterable=index_filterable,
        index_searchable=index_searchable,
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


POINT_PROPERTIES = [
    _number_property("x", "Horizontal coordinate."),
    _number_property("y", "Vertical coordinate."),
]

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

POLYGON_PROPERTIES = [
    _object_array_property(
        "points",
        "Ordered polygon points.",
        nested_properties=POINT_PROPERTIES,
    ),
]

PRINCIPAL_PROPERTIES: list[Property] = [
    _text_property("principal_type", "Principal type discriminator.", searchable=False),
    _text_property("display_name", "Human-readable display name."),
    _bool_property("is_active", "Whether the principal is active."),
    _text_property("external_subject", "OIDC subject for user principals."),
    _text_property("external_issuer", "OIDC issuer for user principals."),
    _text_property("email", "Email address for user principals."),
    _text_property("annotation_type", "Annotation type handled by a model agent.", searchable=False),
    _text_property("role", "Model-agent role prefix.", searchable=False),
    _text_property("model_slug", "Model-agent slot suffix.", searchable=False),
    _text_property("model_version", "Model artifact version.", searchable=False),
    _text_property("registry_source", "Model registry source.", searchable=False),
    _text_property("registry_uri", "Model registry URI.", searchable=False),
]

SOURCE_PROPERTIES: list[Property] = [
    _text_property("source_type", "Source kind.", searchable=False),
    _text_property("uri", "Source URI."),
    _object_property(
        "metadata",
        "Strict source metadata payload.",
        nested_properties=[
            _text_property("library", "Source library identifier.", searchable=False),
            _uuid_property("document", "Document identifier."),
            _uuid_property("page", "Page identifier."),
            _text_property("kramerius_url", "Kramerius source URL.", searchable=False),
            _text_property("entity_id", "Wikidata entity identifier.", searchable=False),
            _text_property("wikidata_url", "Wikidata source URL.", searchable=False),
            _text_property("nlcr_id", "NLCR authority identifier.", searchable=False),
            _text_property("wikimedia_url", "Wikimedia source URL.", searchable=False),
        ],
    ),
]

ENTITY_PROPERTIES: list[Property] = [
    _text_property("entity_type", "Entity type discriminator.", searchable=False),
    _text_property("name", "Entity-level aggregated name value."),
    _text_property("description", "Entity-level aggregated description value."),
    _text_property("short_description", "Entity-level aggregated short description value."),
    _object_array_property(
        "aliases",
        "Entity-level aggregated alias values.",
        nested_properties=[
            _text_property("alias", "Alias value."),
        ],
        index_filterable=True,
        index_searchable=True,
    ),
    _text_property("wikidata_id", "Entity-level aggregated Wikidata ID."),
    _text_property("nlcr_authority_id", "Entity-level aggregated NLCR authority ID."),
]

PAGE_MENTION_PROPERTIES: list[Property] = [
    _text_property("name", "Name of the page mention."),
    _text_property("information", "Information of the page mention."),
    _object_array_property(
        "aliases",
        "Entity-level aggregated alias values.",
        nested_properties=[
            _text_property("alias", "Alias value."),
        ],
        index_filterable=True,
        index_searchable=True,
    ),
    _object_array_property(
        "mentions",
        "Page mention polygon lists.",
        nested_properties=[
            _object_array_property(
                "polygons",
                "Ordered page mention polygons.",
                nested_properties=POLYGON_PROPERTIES,
            )
        ],
    ),
]

DOCUMENT_MENTION_PROPERTIES: list[Property] = [
    _text_property("name", "Aggregated document-level name."),
    _text_property("information", "Aggregated document-level information."),
    _object_array_property(
        "aliases",
        "Entity-level aggregated alias values.",
        nested_properties=[
            _text_property("alias", "Alias value."),
        ],
        index_filterable=True,
        index_searchable=True,
    ),
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

PRINCIPAL_REFERENCES: list[ReferenceProperty] = []
SOURCE_REFERENCES: list[ReferenceProperty] = []
ENTITY_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="principal",
        target_collection=PRINCIPAL_COLLECTION,
        description="Principal that created the entity.",
    )
]
PAGE_MENTION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="document_mention",
        target_collection=DOCUMENT_MENTION_COLLECTION,
        description="Owning document mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the page mention.",
    ),
    ReferenceProperty(
        name="principal",
        target_collection=PRINCIPAL_COLLECTION,
        description="Principal that extracted the page mention.",
    ),
]
DOCUMENT_MENTION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity associated with the document mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the document mention.",
    ),
    ReferenceProperty(
        name="principal",
        target_collection=PRINCIPAL_COLLECTION,
        description="Principal that produced the aggregation.",
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
        name="principal",
        target_collection=PRINCIPAL_COLLECTION,
        description="Principal that performed the detection.",
    ),
]

type CollectionVectorConfig = list[object] | None
type CollectionSpec = tuple[list[Property], list[ReferenceProperty], CollectionVectorConfig]

ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    PAGE_MENTION_COLLECTION: (
        PAGE_MENTION_PROPERTIES,
        PAGE_MENTION_REFERENCES,
        None,
    ),
    DOCUMENT_MENTION_COLLECTION: (
        DOCUMENT_MENTION_PROPERTIES,
        DOCUMENT_MENTION_REFERENCES,
        None,
    ),
    FACE_COLLECTION: (
        FACE_PROPERTIES,
        FACE_REFERENCES,
        default_face_vector_config(),
    ),
}

NON_ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    PRINCIPAL_COLLECTION: (
        PRINCIPAL_PROPERTIES,
        PRINCIPAL_REFERENCES,
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
