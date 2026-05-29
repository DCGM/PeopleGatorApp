from enum import StrEnum


class RecordType(StrEnum):
    face_detection = "face_detection"
    named_entity = "named_entity"
    text_region = "text_region"
    image_region = "image_region"
    grounded_name = "grounded_name"
    grounded_description = "grounded_description"


class ResolverType(StrEnum):
    local_filesystem = "local-filesystem"
    s3 = "s3"
    iiif = "iiif"
    http = "http"
    sparql = "sparql"


class ClusterRole(StrEnum):
    mutable_cluster = "mutable_cluster"
    review_cluster = "review_cluster"
    grounded_cluster = "grounded_cluster"
    authority_cluster = "authority_cluster"
    automatic_cluster = "automatic_cluster"
    search_cluster = "search_cluster"


class HeadConstraint(StrEnum):
    locked = "locked"
    main = "main"
    any = "any"


class LineageType(StrEnum):
    initial = "initial"
    next = "next"
    branch = "branch"
    merge = "merge"
    cluster_merge = "cluster-merge"
    # "split" conflicts with str.split on StrEnum; the DB value stays "split".
    cluster_split = "split"


class ActionType(StrEnum):
    add = "add"
    remove = "remove"


class ActionReason(StrEnum):
    manual_annotation = "manual-annotation"
    automatic_linking = "automatic-linking"


class PrincipalType(StrEnum):
    user = "user"
    service_agent = "service_agent"
