"""Explicit Weaviate collection schema for canonical API persistence."""

from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    ReferenceProperty,
    VectorDistances,
)

from people_gator_api.schemas.enums import AnnotationType

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

PRINCIPAL_COLLECTION = "Principal"
SOURCE_COLLECTION = "Source"
ENTITY_COLLECTION = "Entity"
PAGE_MENTION_COLLECTION = "PageMention"
DOCUMENT_MENTION_COLLECTION = "DocumentMention"
SPAN_COLLECTION = "Span"
FACE_COLLECTION = "Face"
ENTITY_NAME_COLLECTION = "EntityName"
DESCRIPTION_COLLECTION = "Description"

# ---------------------------------------------------------------------------
# Named vector names
# ---------------------------------------------------------------------------

FACE_VECTOR_PREFIX = "face:"
NAME_VECTOR_PREFIX = "name:"
FULLTEXT_VECTOR_PREFIX = "fulltext:"

MICROSOFT_HARRIER_OSS_V1_0_6B = "harrier-oss-v1-0.6b"
GAUNERNST_VIT_SMALL_PATCH8_GAP_112_COSFACE_MS1MV3 = (
    "vit_small_patch8_gap_112.cosface_ms1mv3"
)

DEFAULT_FACE_VECTOR = (
    FACE_VECTOR_PREFIX + GAUNERNST_VIT_SMALL_PATCH8_GAP_112_COSFACE_MS1MV3
)
DEFAULT_NAME_VECTOR = NAME_VECTOR_PREFIX + MICROSOFT_HARRIER_OSS_V1_0_6B
DEFAULT_FULLTEXT_VECTOR = FULLTEXT_VECTOR_PREFIX + MICROSOFT_HARRIER_OSS_V1_0_6B

ANNOTATION_COLLECTION_BY_TYPE: dict[AnnotationType, str] = {
    AnnotationType.document_mention: DOCUMENT_MENTION_COLLECTION,
    AnnotationType.page_mention: PAGE_MENTION_COLLECTION,
    AnnotationType.span: SPAN_COLLECTION,
    AnnotationType.face: FACE_COLLECTION,
    AnnotationType.description: DESCRIPTION_COLLECTION,
        AnnotationType.entity: ENTITY_COLLECTION,
    AnnotationType.entity_name: ENTITY_NAME_COLLECTION,
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
) -> Property:
    return Property(
        name=name,
        data_type=DataType.OBJECT_ARRAY,
        description=description,
        index_filterable=True,
        index_searchable=False,
        nested_properties=nested_properties,
        skip_vectorization=True,
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
    _uuid_property("principal_id", "Primary key of PRINCIPAL.principal_id."),
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
    _uuid_property("source_id", "Primary key of SOURCE.source_id."),
    _text_property("source_type", "Source kind.", searchable=False),
    _text_property("uri", "Source URI."),
    _object_property("metadata", "Strict source metadata payload."),
]

ENTITY_PROPERTIES: list[Property] = [
    _uuid_property("entity_id", "Primary key of ENTITY.entity_id."),
    _uuid_property("principal_id", "Foreign key to PRINCIPAL.principal_id."),
    _text_property("entity_type", "Entity type discriminator.", searchable=False),
    _text_property("name", "Entity-level aggregated name value."),
    _text_property("description", "Entity-level aggregated description value."),
    _text_property("wikidata_id", "Entity-level aggregated Wikidata ID."),
    _text_property("nlcr_authority_id", "Entity-level aggregated NLCR authority ID."),
]

PAGE_MENTION_PROPERTIES: list[Property] = [
    _uuid_property("page_mention_id", "Primary key of PAGE_MENTION.page_mention_id."),
    _text_property("name", "Name of the page mention."),
    _text_property("information", "Information of the page mention."),
    _number_property("confidence", "Extraction confidence."),
    _uuid_property("document_mention_id", "Owning document mention id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
]

DOCUMENT_MENTION_PROPERTIES: list[Property] = [
    _uuid_property("document_mention_id", "Primary key of DOCUMENT_MENTION.document_mention_id."),
    _text_property("name", "Aggregated document-level name."),
    _text_property("information", "Aggregated document-level information."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
]

SPAN_PROPERTIES: list[Property] = [
    _uuid_property("span_id", "Primary key of SPAN.span_id."),
    _text_property("text", "Span text."),
    _object_array_property(
        "polygons",
        "Ordered span polygons.",
        nested_properties=POLYGON_PROPERTIES,
    ),
    _uuid_property("page_mention_id", "Owning page mention id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
]

FACE_PROPERTIES: list[Property] = [
    _uuid_property("detection_id", "Primary key of FACE.detection_id."),
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
    _uuid_property("source_id", "Source id."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
    _uuid_property("entity_id", "Entity id."),
]

DESCRIPTION_PROPERTIES: list[Property] = [
    _uuid_property("description_id", "Primary key of DESCRIPTION.description_id."),
    _text_property("text", "Description text."),
    _text_property("language", "Language code.", searchable=False),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
]

ENTITY_NAME_PROPERTIES: list[Property] = [
    _uuid_property("entity_name_id", "Primary key of ENTITY_NAME.entity_name_id."),
    _text_property("name", "Name value."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
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
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Model agent that extracted the page mention.",
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
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Model agent that produced the aggregation.",
    ),
]
SPAN_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="page_mention",
        target_collection=PAGE_MENTION_COLLECTION,
        description="Owning page mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the span.",
    ),
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity associated with the span.",
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
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Model agent that performed the detection.",
    ),
]
DESCRIPTION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity associated with the description.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the description.",
    ),
]
ENTITY_NAME_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="entity",
        target_collection=ENTITY_COLLECTION,
        description="Entity associated with the name.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the name.",
    ),
]

type CollectionVectorConfig = list[object] | None
type CollectionSpec = tuple[list[Property], list[ReferenceProperty], CollectionVectorConfig]

ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    PAGE_MENTION_COLLECTION: (
        PAGE_MENTION_PROPERTIES,
        PAGE_MENTION_REFERENCES,
        default_name_plus_fulltext_vector_config(),
    ),
    DOCUMENT_MENTION_COLLECTION: (
        DOCUMENT_MENTION_PROPERTIES,
        DOCUMENT_MENTION_REFERENCES,
        default_name_plus_fulltext_vector_config(),
    ),
    SPAN_COLLECTION: (
        SPAN_PROPERTIES,
        SPAN_REFERENCES,
        default_name_vector_config(),
    ),
    ENTITY_NAME_COLLECTION: (
        ENTITY_NAME_PROPERTIES,
        ENTITY_NAME_REFERENCES,
        default_name_vector_config(),
    ),
    DESCRIPTION_COLLECTION: (
        DESCRIPTION_PROPERTIES,
        DESCRIPTION_REFERENCES,
        default_fulltext_vector_config(),
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
