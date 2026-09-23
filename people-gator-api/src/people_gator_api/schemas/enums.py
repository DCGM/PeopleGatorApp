from enum import StrEnum


class EntityType(StrEnum):
    """Entity type discriminator for normalized identity classes."""

    person = "person"  # Person entity type


class SourceKind(StrEnum):
    """Physical type of a SOURCE record."""

    page = "page"  # Page source
    document = "document"  # Document source
    image = "image"  # Image source


class FaceEmbeddingModel(StrEnum):
    """Known face embedding models with named vectors in the Face collection."""

    gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3 = (
        "vit_small_patch8_gap_112.cosface_ms1mv3"
    )


DEFAULT_FACE_EMBEDDING_MODEL = (
    FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3.value
)


class ScoreAggregation(StrEnum):
    """How per-modality scores are aggregated into a single entity score."""

    min = "min"  # Minimum score aggregation
    max = "max"  # Maximum score aggregation
    average = "average"  # Average score aggregation


class ScoreFusion(StrEnum):
    """How scores from different modalities are fused into a single entity score."""

    rrf = "rrf"  # Reciprocal Rank Fusion


class Language(StrEnum):
    """Languages supported by the translation endpoint."""

    czech = "cs"  # Czech language
    english = "en"  # English language
    german = "de"  # German language


__all__ = [
    "EntityType",
    "SourceKind",
    "FaceEmbeddingModel",
    "DEFAULT_FACE_EMBEDDING_MODEL",
    "ScoreAggregation",
    "ScoreFusion",
    "Language",
]
