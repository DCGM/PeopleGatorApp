"""Explicit Weaviate v4 collection schema definitions.

Two collections are managed here:

AnnotationEmbedding
    One document per (annotation_type, annotation_id) pair that carries an
    embedding vector.  Supports nearest-neighbour lookup for individual
    face detections and named-entity spans, as well as filter-then-rank
    queries scoped to a particular identity or annotation type.

IdentitySnapshot
    One document per identity, updated whenever the materialised
    LINK_CONSENSUS rows change.  Uses *named vectors* so that face and
    name signals can be queried independently or combined with manually
    specified weights, matching the product-spec requirement for weighted
    multi-modal search.
"""

from weaviate.classes.config import (
    Configure,
    DataType,
    Property,
    VectorDistances,
)

# ---------------------------------------------------------------------------
# Collection name constants
# ---------------------------------------------------------------------------

ANNOTATION_EMBEDDING_COLLECTION: str = "AnnotationEmbedding"
IDENTITY_SNAPSHOT_COLLECTION: str = "IdentitySnapshot"

# Named-vector keys used inside IdentitySnapshot
FACE_VECTOR: str = "face"
NAME_VECTOR: str = "name"

# ---------------------------------------------------------------------------
# AnnotationEmbedding schema
# ---------------------------------------------------------------------------

ANNOTATION_EMBEDDING_PROPERTIES: list[Property] = [
    Property(
        name="annotation_type",
        data_type=DataType.TEXT,
        description=(
            "Annotation type enum value: named_entity, detection, "
            "description, alternative_name."
        ),
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="annotation_id",
        data_type=DataType.UUID,
        description="UUID of the annotation row (entity_id, detection_id, etc.).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="FK to SOURCE — the document this annotation was derived from.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="identity_id",
        data_type=DataType.UUID,
        description=(
            "The identity this annotation is currently linked to.  Reflects "
            "the latest LINK_CONSENSUS 'include' row for this annotation."
        ),
        index_filterable=True,
        index_searchable=False,
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
        name="model_agent_id",
        data_type=DataType.UUID,
        description="FK to PRINCIPAL (model agent) that produced this annotation.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]


def annotation_embedding_vector_config():
    """Return the vector index configuration for AnnotationEmbedding.

    Uses a single un-named HNSW vector with cosine distance, which is
    the standard metric for normalised face and text embedding models.
    Vectorizer is NONE because all vectors are provided by the caller.
    """
    return Configure.Vectors.self_provided(
        vector_index_config=Configure.VectorIndex.hnsw(
            distance_metric=VectorDistances.COSINE,
        )
    )


# ---------------------------------------------------------------------------
# IdentitySnapshot schema
# ---------------------------------------------------------------------------

IDENTITY_SNAPSHOT_PROPERTIES: list[Property] = [
    Property(
        name="identity_id",
        data_type=DataType.UUID,
        description="FK to IDENTITY.identity_id — stable identity of the person.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="detection_count",
        data_type=DataType.INT,
        description="Number of detection annotations in this identity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="named_entity_count",
        data_type=DataType.INT,
        description="Number of named_entity annotations in this identity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="description_count",
        data_type=DataType.INT,
        description="Number of description annotations in this identity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="alternative_name_count",
        data_type=DataType.INT,
        description="Number of alternative_name annotations in this identity snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
]


def identity_snapshot_named_vector_configs():
    """Return the named-vector configuration list for IdentitySnapshot.

    Two named vectors are defined:
      face  — centroid of all detection embedding vectors in the identity.
      name  — centroid of all named-entity embedding vectors in the identity.

    Both use HNSW with cosine distance.  Vectorizer is NONE because centroid
    vectors are computed by IdentitySyncService and injected at upsert time.
    """
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
