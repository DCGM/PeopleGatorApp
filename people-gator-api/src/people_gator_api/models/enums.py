from enum import StrEnum

class AnnotationType(StrEnum):
    """Annotation entities in the simplified ER diagram."""
    mention = "mention"
    information = "information"
    document_mention = "document_mention"
    face = "face"
    description = "description"
    person_name = "name"


class SourceKind(StrEnum):
    """Physical type of a SOURCE record."""
    page = "page"
    image = "image"
    authority = "authority"


class RecordSource(StrEnum):
    """Origin of external content records."""
    wikidata = "wikidata"
    wikicommons = "wikicommons"
    nlcr = "nlcr"
    obalkyknih = "obalkyknih"
    kramerius = "kramerius"


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
