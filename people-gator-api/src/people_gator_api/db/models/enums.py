from enum import StrEnum


class EvidenceType(StrEnum):
    """Discriminator for EVIDENCE rows and vector-store documents."""

    face_detection = "face_detection"
    named_entity = "named_entity"
    text_region = "text_region"
    grounded_name = "grounded_name"
    grounded_description = "grounded_description"
    authority_identifier = "authority_identifier"


class ResolverType(StrEnum):
    """Discriminator for SOURCE_SCHEMA.resolver_type."""

    db_source_table_row = "db-source-table-row"
    s3_image = "s3-image"
    http_image = "http-image"
    fsspec_image = "fsspec-image"
    fsspec_pagexml = "fsspec-pagexml"
    s3_table = "s3-table"


class ProviderType(StrEnum):
    """Coarse provenance identifier for SOURCE rows."""

    kramerius = "kramerius"
    nkcr = "nkcr"
    wikimedia = "wikimedia"
    local = "local"


class ClusterRole(StrEnum):
    """Cluster role stored on VERSION and read via head_version_id."""

    saved_search = "saved_search"
    automatic_cluster = "automatic_cluster"
    manual_cluster = "manual_cluster"
    authority_cluster = "authority_cluster"
    grounded_cluster = "grounded_cluster"


class OperationType(StrEnum):
    """Types of directed edges in the VERSION DAG."""

    empty = "empty"
    stage = "stage"
    branch = "branch"
    union = "union"
    intersection = "intersection"
    # "split" would conflict with str.split on StrEnum; use a safe alias.
    cluster_split = "split"
    conflict_free_join = "conflict_free_join"


class DeltaType(StrEnum):
    """Whether a DELTA adds or removes evidence from a VERSION."""

    add = "add"
    remove = "remove"


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


class TaskRole(StrEnum):
    """What the assignee is expected to do on a TASK."""

    annotate = "annotate"
    review = "review"
    verify = "verify"


class TaskStatus(StrEnum):
    """Lifecycle state of a TASK."""

    pending = "pending"
    submitted = "submitted"
    review = "review"
    closed = "closed"


class ProcessingStatus(StrEnum):
    """Lifecycle state of a SOURCE_PROCESSING job."""

    queued = "queued"
    in_progress = "in_progress"
    complete = "complete"
    failed = "failed"
