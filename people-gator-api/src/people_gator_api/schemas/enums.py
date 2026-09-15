from enum import StrEnum


class AnnotationType(StrEnum):
    """Annotation entities in the simplified ER diagram."""

    entity = "entity"
    document_mention = "document_mention"
    page_mention = "page_mention"
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
    wikidata = "wikidata"
    wikimedia = "wikimedia"
    obalkyknih = "obalkyknih"
    nlcr = "nlcr"


class PrincipalType(StrEnum):
    """Polymorphic discriminator for PRINCIPAL rows."""

    user = "user"
    service_agent = "service_agent"
    model_agent = "model_agent"


class RegistrySource(StrEnum):
    """Model registry that hosts a MODEL_AGENT artifact."""

    mlflow = "mlflow"
    huggingface = "huggingface"
    local = "local"


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
