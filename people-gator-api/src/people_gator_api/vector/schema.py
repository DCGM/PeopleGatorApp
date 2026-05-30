"""Explicit Weaviate v4 collection schema definitions.

Two collections are managed here:

RecordEmbedding
    One document per (record_id, record_version_id) pair that carries an
    embedding vector.  Supports nearest-neighbour lookup for individual
    face detections and named-entity spans, as well as filter-then-rank
    queries scoped to a particular cluster or record type.

ClusterSnapshot
    One document per cluster, updated whenever the materialised MEMBERSHIP
    table changes.  Uses *named vectors* so that face and name signals can
    be queried independently or combined with manually specified weights,
    matching the product-spec requirement for weighted multi-modal search.
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

RECORD_EMBEDDING_COLLECTION: str = "RecordEmbedding"
CLUSTER_SNAPSHOT_COLLECTION: str = "ClusterSnapshot"

# Named-vector keys used inside ClusterSnapshot
FACE_VECTOR: str = "face"
NAME_VECTOR: str = "name"

# ---------------------------------------------------------------------------
# RecordEmbedding schema
# ---------------------------------------------------------------------------

RECORD_EMBEDDING_PROPERTIES: list[Property] = [
    Property(
        name="record_id",
        data_type=DataType.UUID,
        description="UUID of the RECORD row (record_id column).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="record_version_id",
        data_type=DataType.UUID,
        description="UUID of the specific RECORD version (record_version_id column).",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="record_type",
        data_type=DataType.TEXT,
        description=(
            "Record type enum value: face_detection, named_entity, "
            "text_region, image_region, grounded_name, grounded_description."
        ),
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="source_id",
        data_type=DataType.UUID,
        description="FK to SOURCE — the document this record was derived from.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="cluster_id",
        data_type=DataType.UUID,
        description=(
            "The cluster this record is currently a member of.  Reflects the "
            "latest MEMBERSHIP row for this record."
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
        name="model_version",
        data_type=DataType.TEXT,
        description="Identifier of the model that produced this record.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="membership_weight",
        data_type=DataType.NUMBER,
        description="Weight of this record's membership in the associated cluster.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="membership_reason",
        data_type=DataType.TEXT,
        description="Reason for the membership action: manual-annotation or automatic-linking.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
]


def record_embedding_vector_config():
    """Return the vector index configuration for RecordEmbedding.

    Uses a single un-named HNSW vector with cosine distance, which is
    the standard metric for normalised face and text embedding models.
    Vectorizer is NONE because all vectors are provided by the caller.
    """
    return Configure.Vectorizer.none()


# ---------------------------------------------------------------------------
# ClusterSnapshot schema
# ---------------------------------------------------------------------------

CLUSTER_SNAPSHOT_PROPERTIES: list[Property] = [
    Property(
        name="cluster_id",
        data_type=DataType.UUID,
        description="FK to CLUSTER.cluster_id — stable identity of the cluster.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="cluster_role",
        data_type=DataType.TEXT,
        description=(
            "Denormalised cluster role: mutable_cluster, review_cluster, "
            "grounded_cluster, authority_cluster, automatic_cluster, search_cluster."
        ),
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="as_of_version_id",
        data_type=DataType.UUID,
        description="The VERSION.version_id this snapshot was derived from.",
        index_filterable=True,
        index_searchable=False,
        skip_vectorization=True,
    ),
    Property(
        name="face_count",
        data_type=DataType.INT,
        description="Number of face_detection records in this cluster snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="named_entity_count",
        data_type=DataType.INT,
        description="Number of named_entity records in this cluster snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
    Property(
        name="text_region_count",
        data_type=DataType.INT,
        description="Number of text_region records in this cluster snapshot.",
        index_filterable=True,
        index_range_filters=True,
        skip_vectorization=True,
    ),
]


def cluster_snapshot_named_vector_configs():
    """Return the named-vector configuration list for ClusterSnapshot.

    Two named vectors are defined:
      face  — centroid of all face-detection embedding vectors in the cluster.
      name  — centroid of all named-entity embedding vectors in the cluster.

    Both use HNSW with cosine distance.  Vectorizer is NONE because centroid
    vectors are computed by ClusterSyncService and injected at upsert time.
    """
    return [
        Configure.NamedVectors.none(
            name=FACE_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
        Configure.NamedVectors.none(
            name=NAME_VECTOR,
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=VectorDistances.COSINE,
            ),
        ),
    ]
