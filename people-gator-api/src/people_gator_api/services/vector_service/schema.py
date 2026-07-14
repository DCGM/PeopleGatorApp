"""Explicit Weaviate collection schema for canonical API persistence."""

from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    ReferenceProperty,
    VectorDistances,
)

from people_gator_api.models.enums import AnnotationType

# ---------------------------------------------------------------------------
# Collection names
# ---------------------------------------------------------------------------

PRINCIPAL_COLLECTION = "Principal"
SOURCE_COLLECTION = "Source"
ENTITY_COLLECTION = "Entity"
MENTION_COLLECTION = "Mention"
INFORMATION_COLLECTION = "Information"
DOCUMENT_MENTION_COLLECTION = "DocumentMention"
FACE_COLLECTION = "Face"
DESCRIPTION_COLLECTION = "Description"
NAME_COLLECTION = "Name"
SEARCH_PROFILE_COLLECTION = "SearchProfile"
SEARCH_PROFILE_MODALITY_COLLECTION = "SearchProfileModality"

# Named vectors
FACE_VECTOR = "face:default"
NAME_VECTOR = "name:default"
DESCRIPTION_VECTOR = "description:default"
DOCUMENT_MENTION_NAME_VECTOR = "name:default"
DOCUMENT_MENTION_INFORMATION_VECTOR = "information:default"

ANNOTATION_COLLECTION_BY_TYPE: dict[AnnotationType, str] = {
    AnnotationType.person_name: NAME_COLLECTION,
    AnnotationType.description: DESCRIPTION_COLLECTION,
    AnnotationType.information: INFORMATION_COLLECTION,
    AnnotationType.mention: MENTION_COLLECTION,
    AnnotationType.face: FACE_COLLECTION,
    AnnotationType.document_mention: DOCUMENT_MENTION_COLLECTION,
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


def _number_array_property(name: str, description: str) -> Property:
    return Property(
        name=name,
        data_type=DataType.NUMBER_ARRAY,
        description=description,
        index_filterable=False,
        index_searchable=False,
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


def default_vector_config(
    name: str
) -> object:
    return Configure.NamedVectors.none(
        name=name,
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        )
    )


def entity_named_vector_configs() -> list[object]:
    return [
        Configure.Vectors.self_provided(
            name=NAME_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
        Configure.Vectors.self_provided(
            name=DESCRIPTION_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    ]


def document_mention_named_vector_config() -> list[object]:
    return [
        Configure.Vectors.self_provided(
            name=DOCUMENT_MENTION_NAME_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
        Configure.Vectors.self_provided(
            name=DOCUMENT_MENTION_INFORMATION_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    ]


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
    _object_property("metadata", "Arbitrary source metadata."),
]

ENTITY_PROPERTIES: list[Property] = [
    _uuid_property("entity_id", "Primary key of ENTITY.entity_id."),
    _uuid_property("principal_id", "Foreign key to PRINCIPAL.principal_id."),
    _text_property("name", "Entity-level aggregated name value."),
    _text_property("description", "Entity-level aggregated description value."),
    _int_property("name_count", "Number of linked NAME rows."),
    _int_property("description_count", "Number of linked DESCRIPTION rows."),
]

MENTION_PROPERTIES: list[Property] = [
    _uuid_property("mention_id", "Primary key of MENTION.mention_id."),
    _text_property("text", "Mention text span."),
    _int_property("offset_start", "Source text start offset."),
    _int_property("offset_end", "Source text end offset."),
    _object_array_property(
        "polygons",
        "Optional mention polygons.",
        nested_properties=POLYGON_PROPERTIES,
    ),
    _number_property("confidence", "Extraction confidence."),
    _uuid_property("document_mention_id", "Owning document mention id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
    _number_array_property("embedding", "Stored mention embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
]

INFORMATION_PROPERTIES: list[Property] = [
    _uuid_property("information_id", "Primary key of INFORMATION.information_id."),
    _text_property("text", "Information text."),
    _uuid_property("document_mention_id", "Owning document mention id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
    _number_array_property("embedding", "Stored information embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
]

DOCUMENT_MENTION_PROPERTIES: list[Property] = [
    _uuid_property("document_mention_id", "Primary key of DOCUMENT_MENTION.document_mention_id."),
    _text_property("name", "Aggregated document-level name."),
    _text_property("information", "Aggregated document-level information."),
    _uuid_property("model_agent_id", "Model-agent principal id."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
    _number_array_property("embedding", "Stored document-mention embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
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
    _number_array_property("embedding", "Stored face embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
]

DESCRIPTION_PROPERTIES: list[Property] = [
    _uuid_property("description_id", "Primary key of DESCRIPTION.description_id."),
    _text_property("text", "Description text."),
    _text_property("language", "Language code.", searchable=False),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
    _number_array_property("embedding", "Stored description embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
]

NAME_PROPERTIES: list[Property] = [
    _uuid_property("name_id", "Primary key of NAME.name_id."),
    _text_property("name", "Name value."),
    _uuid_property("source_id", "Source id."),
    _uuid_property("entity_id", "Entity id."),
    _number_array_property("embedding", "Stored name embedding."),
    _text_property("model_identifier", "Embedding model identifier.", searchable=False),
]

SEARCH_PROFILE_PROPERTIES: list[Property] = [
    _uuid_property("profile_id", "Primary key of SEARCH_PROFILE.profile_id."),
    _text_property("profile_name", "Search profile name."),
    _text_property("description", "Search profile description."),
    _uuid_property("owner_id", "Owning principal id."),
    _bool_property("is_public", "Whether the profile is public."),
    _bool_property("is_system", "Whether the profile is system-managed."),
]

SEARCH_PROFILE_MODALITY_PROPERTIES: list[Property] = [
    _uuid_property("modality_id", "Synthetic primary key for SEARCH_PROFILE_MODALITY."),
    _uuid_property("profile_id", "Owning profile id."),
    _text_property("annotation_type", "Annotation type for this modality.", searchable=False),
    _uuid_property("model_id", "Pinned model-agent principal id."),
    _number_property("weight", "Relative modality weight."),
    _number_property("min_confidence", "Optional minimum annotation confidence."),
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
MENTION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="document_mention",
        target_collection=DOCUMENT_MENTION_COLLECTION,
        description="Owning document mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the mention.",
    ),
    ReferenceProperty(
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Model agent that extracted the mention.",
    ),
]
INFORMATION_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="document_mention",
        target_collection=DOCUMENT_MENTION_COLLECTION,
        description="Owning document mention.",
    ),
    ReferenceProperty(
        name="source",
        target_collection=SOURCE_COLLECTION,
        description="Source containing the information.",
    ),
    ReferenceProperty(
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Model agent that extracted the information.",
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
NAME_REFERENCES: list[ReferenceProperty] = [
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
SEARCH_PROFILE_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="owner",
        target_collection=PRINCIPAL_COLLECTION,
        description="Owner of the search profile.",
    )
]
SEARCH_PROFILE_MODALITY_REFERENCES: list[ReferenceProperty] = [
    ReferenceProperty(
        name="profile",
        target_collection=SEARCH_PROFILE_COLLECTION,
        description="Owning search profile.",
    ),
    ReferenceProperty(
        name="model_agent",
        target_collection=PRINCIPAL_COLLECTION,
        description="Pinned model-agent principal.",
    ),
]

type CollectionSpec = tuple[list[Property], list[ReferenceProperty], object]

ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    NAME_COLLECTION: (
        NAME_PROPERTIES, 
        NAME_REFERENCES, 
        default_vector_config(name=NAME_VECTOR)
    ),
    DESCRIPTION_COLLECTION: (
        DESCRIPTION_PROPERTIES,
        DESCRIPTION_REFERENCES,
        default_vector_config(name=DESCRIPTION_VECTOR),
    ),
    INFORMATION_COLLECTION: (
        INFORMATION_PROPERTIES,
        INFORMATION_REFERENCES,
        default_vector_config(name=DOCUMENT_MENTION_INFORMATION_VECTOR),
    ),
    MENTION_COLLECTION: (
        MENTION_PROPERTIES, 
        MENTION_REFERENCES, 
        default_vector_config(name=DOCUMENT_MENTION_NAME_VECTOR)
    ),
    FACE_COLLECTION: (
        FACE_PROPERTIES, 
        FACE_REFERENCES, 
        default_vector_config(name=FACE_VECTOR)
    ),
    DOCUMENT_MENTION_COLLECTION: (
        DOCUMENT_MENTION_PROPERTIES,
        DOCUMENT_MENTION_REFERENCES,
        document_mention_named_vector_config(),
    ),
}

NON_ANNOTATION_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    PRINCIPAL_COLLECTION: (
        PRINCIPAL_PROPERTIES, 
        PRINCIPAL_REFERENCES, 
        None
    ),
    SOURCE_COLLECTION: (
        SOURCE_PROPERTIES, 
        SOURCE_REFERENCES, 
        None
    ),
    ENTITY_COLLECTION: (
        ENTITY_PROPERTIES, 
        ENTITY_REFERENCES, 
        entity_named_vector_configs()
    ),
    SEARCH_PROFILE_COLLECTION: (
        SEARCH_PROFILE_PROPERTIES,
        SEARCH_PROFILE_REFERENCES,
        None
    ),
    SEARCH_PROFILE_MODALITY_COLLECTION: (
        SEARCH_PROFILE_MODALITY_PROPERTIES,
        SEARCH_PROFILE_MODALITY_REFERENCES,
        None
    ),
}

ALL_COLLECTION_SPECS: dict[str, CollectionSpec] = {
    **NON_ANNOTATION_COLLECTION_SPECS,
    **ANNOTATION_COLLECTION_SPECS,
}


def collection_for_annotation_type(annotation_type: AnnotationType) -> str:
    return ANNOTATION_COLLECTION_BY_TYPE[annotation_type]
