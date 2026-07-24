from enum import StrEnum

class AnnotationType(StrEnum):
    """Annotation entities in the simplified ER diagram."""
    entity = "entity"
    document_mention = "document_mention"
    page_mention = "page_mention"
    span = "span"
    face = "face"
    description = "description"
    entity_name = "entity_name"


class SourceKind(StrEnum):
    """Physical type of a SOURCE record."""

    page = "page"
    document = "document"
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
