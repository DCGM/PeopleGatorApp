"""Explicit Weaviate v4 collection schema definitions.

The vector layer mirrors relational annotation tables into per-entity
collections so filtering can run directly in Weaviate without a relational
lookup roundtrip:

- Name
- Description
- Information
- Mention
- Face
- DocumentMention (with named vectors for name and information)

EntitySnapshot remains as a derived read model for weighted entity-level
search over face/name centroids.
"""

from people_gator_api.models.enums import AnnotationType
from weaviate.classes.config import Configure, DataType, Property, VectorDistances

# ---------------------------------------------------------------------------
# Collection name constants
# ---------------------------------------------------------------------------

NAME_COLLECTION: str = "Name"
DESCRIPTION_COLLECTION: str = "Description"
INFORMATION_COLLECTION: str = "Information"
MENTION_COLLECTION: str = "Mention"
FACE_COLLECTION: str = "Face"
DOCUMENT_MENTION_COLLECTION: str = "DocumentMention"
ENTITY_COLLECTION: str = "Entity"

ENTITY_SNAPSHOT_COLLECTION: str = "EntitySnapshot"

# Named-vector keys used inside EntitySnapshot
FACE_VECTOR: str = "face"
NAME_VECTOR: str = "name"
DESCRIPTION_VECTOR: str = "description"

# Named-vector keys used inside DocumentMention
DOCUMENT_MENTION_NAME_VECTOR: str = "name"
DOCUMENT_MENTION_INFORMATION_VECTOR: str = "information"

ANNOTATION_COLLECTION_BY_TYPE: dict[AnnotationType, str] = {
    AnnotationType.person_name: NAME_COLLECTION,
    AnnotationType.description: DESCRIPTION_COLLECTION,
    AnnotationType.information: INFORMATION_COLLECTION,
    AnnotationType.mention: MENTION_COLLECTION,
    AnnotationType.face: FACE_COLLECTION,
    AnnotationType.document_mention: DOCUMENT_MENTION_COLLECTION,
}

# ---------------------------------------------------------------------------
# Per-annotation collection schemas
# ---------------------------------------------------------------------------

NAME_PROPERTIES: list[Property] = [
    Property(
        name="name_id",
        data_type=DataType.UUID,
        description="Primary key of NAME.name_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="name",
        data_type=DataType.TEXT,
        description="Name text value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="Foreign key to ENTITY.entity_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]

DESCRIPTION_PROPERTIES: list[Property] = [
    Property(
        name="description_id",
        data_type=DataType.UUID,
        description="Primary key of DESCRIPTION.description_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="text",
        data_type=DataType.TEXT,
        description="Description text value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="language",
        data_type=DataType.TEXT,
        description="Language code.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="Foreign key to ENTITY.entity_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]

INFORMATION_PROPERTIES: list[Property] = [
    Property(
        name="information_id",
        data_type=DataType.UUID,
        description="Primary key of INFORMATION.information_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="text",
        data_type=DataType.TEXT,
        description="Information text value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="model_agent_id",
        data_type=DataType.UUID,
        description="Foreign key to PRINCIPAL.principal_id (model agent).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]

MENTION_PROPERTIES: list[Property] = [
    Property(
        name="mention_id",
        data_type=DataType.UUID,
        description="Primary key of MENTION.mention_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="text",
        data_type=DataType.TEXT,
        description="Mention text value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="offset_start",
        data_type=DataType.INT,
        description="Start character offset in source text.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="offset_end",
        data_type=DataType.INT,
        description="End character offset in source text.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="confidence",
        data_type=DataType.NUMBER,
        description="Inference confidence from the originating model.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="polygons_json",
        data_type=DataType.TEXT,
        description="Serialized optional mention polygon coordinates.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="model_agent_id",
        data_type=DataType.UUID,
        description="Foreign key to PRINCIPAL.principal_id (model agent).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]

FACE_PROPERTIES: list[Property] = [
    Property(
        name="detection_id",
        data_type=DataType.UUID,
        description="Primary key of FACE.detection_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="model_agent_id",
        data_type=DataType.UUID,
        description="Foreign key to PRINCIPAL.principal_id (model agent).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="Foreign key to SOURCE.source_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="Foreign key to ENTITY.entity_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="confidence",
        data_type=DataType.NUMBER,
        description="Detection confidence.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="bbox_x",
        data_type=DataType.INT,
        description="Face bounding box x.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="bbox_y",
        data_type=DataType.INT,
        description="Face bounding box y.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="bbox_width",
        data_type=DataType.INT,
        description="Face bounding box width.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="bbox_height",
        data_type=DataType.INT,
        description="Face bounding box height.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="keypoints_json",
        data_type=DataType.TEXT,
        description="Serialized keypoints payload.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
]

DOCUMENT_MENTION_PROPERTIES: list[Property] = [
    Property(
        name="document_mention_id",
        data_type=DataType.UUID,
        description="Primary key of DOCUMENT_MENTION.document_mention_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="name",
        data_type=DataType.TEXT,
        description="Aggregated name value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="information",
        data_type=DataType.TEXT,
        description="Aggregated information value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="model_agent_id",
        data_type=DataType.UUID,
        description="Foreign key to PRINCIPAL.principal_id (model agent).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="Foreign key to ENTITY.entity_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]


def default_vector_config():
    """Return a default single-vector HNSW cosine config."""
    return Configure.Vectors.self_provided(
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        )
    )


def document_mention_named_vector_config():
    """Return named vectors for DocumentMention name and information embeddings."""
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


ANNOTATION_COLLECTION_SPECS: dict[
    str,
    tuple[list[Property], object],
] = {
    NAME_COLLECTION: (NAME_PROPERTIES, default_vector_config()),
    DESCRIPTION_COLLECTION: (DESCRIPTION_PROPERTIES, default_vector_config()),
    INFORMATION_COLLECTION: (INFORMATION_PROPERTIES, default_vector_config()),
    MENTION_COLLECTION: (MENTION_PROPERTIES, default_vector_config()),
    FACE_COLLECTION: (FACE_PROPERTIES, default_vector_config()),
    DOCUMENT_MENTION_COLLECTION: (
        DOCUMENT_MENTION_PROPERTIES,
        document_mention_named_vector_config(),
    ),
}


# ---------------------------------------------------------------------------
# EntitySnapshot schema
# ---------------------------------------------------------------------------

ENTITY_SNAPSHOT_PROPERTIES: list[Property] = [
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="FK to ENTITY.entity_id - stable identity of the person.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="face_count",
        data_type=DataType.INT,
        description="Number of face annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="mention_count",
        data_type=DataType.INT,
        description="Number of mention annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="information_count",
        data_type=DataType.INT,
        description="Number of information annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="document_mention_count",
        data_type=DataType.INT,
        description="Number of document_mention annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="description_count",
        data_type=DataType.INT,
        description="Number of description annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="name_count",
        data_type=DataType.INT,
        description="Number of name annotations in this entity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
]


def entity_snapshot_named_vector_configs():
    """Return named-vector configuration list for EntitySnapshot."""
    return [
        Configure.Vectors.self_provided(
            name=FACE_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
        Configure.Vectors.self_provided(
            name=NAME_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    ]


ENTITY_PROPERTIES: list[Property] = [
    Property(
        name="entity_id",
        data_type=DataType.UUID,
        description="Primary key of ENTITY.entity_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="principal_id",
        data_type=DataType.UUID,
        description="Foreign key to PRINCIPAL.principal_id.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="name",
        data_type=DataType.TEXT,
        description="Entity-level aggregated name value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="description",
        data_type=DataType.TEXT,
        description="Entity-level aggregated description value.",
        index_filterable=True,
        index_searchable=True,
        skip_vectorization=True,
    ),
    Property(
        name="name_count",
        data_type=DataType.INT,
        description="Number of linked NAME rows.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="description_count",
        data_type=DataType.INT,
        description="Number of linked DESCRIPTION rows.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
]


def entity_named_vector_configs() -> list[object]:
    """Return named vectors for entity-level name and description search."""
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


# Backward compatibility alias for older imports.
IDENTITY_SNAPSHOT_COLLECTION = ENTITY_SNAPSHOT_COLLECTION
IDENTITY_SNAPSHOT_PROPERTIES = ENTITY_SNAPSHOT_PROPERTIES
identity_snapshot_named_vector_configs = entity_snapshot_named_vector_configs


def collection_for_annotation_type(annotation_type: AnnotationType) -> str:
    """Return the Weaviate collection name for an annotation type."""
    return ANNOTATION_COLLECTION_BY_TYPE[annotation_type]
