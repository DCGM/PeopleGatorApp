from enum import StrEnum

class AnnotationType(StrEnum):
    """Type of annotation (spec §2.2)."""
    named_entity = "named_entity"
    detection = "detection"
    description = "description"
    alternative_name = "alternative_name"

class Decision(StrEnum):
    """An annotator's verdict on whether an annotation belongs to an identity.

    Used in LINK_DECISION and LINK_CONSENSUS records (spec §2.6).
    """
    include = "include"
    exclude = "exclude"
    uncertain = "uncertain"
    garbage = "garbage"


class ConsensusMethod(StrEnum):
    """Strategy used to produce a LINK_CONSENSUS from multiple decisions.

    Exact implementation is application logic; the method used is stored
    directly on the consensus record (spec §2.6.2).
    """
    union = "union"
    majority = "majority"
    reviewer = "reviewer"


class NameType(StrEnum):
    """Type of variant for an ALTERNATIVE_NAME record (spec §2.5)."""
    full = "full"
    alternative = "alternative"


class SourceKind(StrEnum):
    """Physical type of a SOURCE record (spec §2.7).

    Determines what kind of artifact the source represents and how its
    metadata is interpreted.
    """
    page = "page"
    image = "image"
    authority = "authority"


class RecordSource(StrEnum):
    """Origin of a DESCRIPTION or ALTERNATIVE_NAME record (spec §2.4, §2.5).

    Indicates whether the record came from an authority sync, a Wikidata
    import, or manual curation.
    """
    wikidata = "wikidata"
    wikicommons = "wikicommons"
    nlcr = "nlcr"
    obalkyknih = "obalkyknih"
    kramerius = "kramerius"
    


class EntityType(StrEnum):
    """Coarse type of a NAMED_ENTITY mention (spec §2.2).

    Follows common NER label sets. Only ``person`` is expected for
    identity-centric workflows, but the full set is retained for
    provenance fidelity when ingesting raw NER output.
    """
    person = "person"


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
