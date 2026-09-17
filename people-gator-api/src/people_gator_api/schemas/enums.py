from enum import StrEnum


class AnnotationType(StrEnum):
    """Annotation entities in the simplified ER diagram."""

    entity = "entity"
    face = "face"


class EntityType(StrEnum):
    """Entity type discriminator for normalized identity classes."""

    person = "person"
    place = "place"
    date = "date"


class SourceKind(StrEnum):
    """Physical type of a SOURCE record."""

    page = "page"
    document = "document"
    image = "image"


class FaceEmbeddingModel(StrEnum):
    """Known face embedding models with named vectors in the Face collection."""

    gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3 = (
        "vit_small_patch8_gap_112.cosface_ms1mv3"
    )


DEFAULT_FACE_EMBEDDING_MODEL = (
    FaceEmbeddingModel.gaunernst_vit_small_patch8_gap_112_cosface_ms1mv3
)


class ScoreAggregation(StrEnum):
    """How per-face matching scores are aggregated into a single entity score."""

    min = "min"
    max = "max"
    average = "average"
