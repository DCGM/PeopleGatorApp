"""Read explicit preconditions when exercising older mutation scenarios.

Conflict tests supply deliberately stale versions themselves. These helpers do
not retry mutations and use 1 only for deliberately missing-object test targets.
"""


async def read_version(repository, object_id):
    getter = getattr(repository, "get", None) or repository.get_source
    record = await getter(object_id)
    return record.version if record is not None else 1


async def read_versions(repository, object_ids):
    return {object_id: await read_version(repository, object_id) for object_id in object_ids}


def versioned_targets(versions):
    from people_gator_api.schemas.common import VersionedTarget

    return [
        VersionedTarget(object_id=identity, version=version)
        for identity, version in versions.items()
    ]


def merge_targets(versions, target):
    return {
        "version": versions[target],
        "sources": versioned_targets(
            {
                identity: version
                for identity, version in versions.items()
                if identity != target
            }
            or {target: versions[target]}
        ),
    }


def merge_request(patch, source_ids):
    # Preserve deliberately invalid duplicate/self/missing targets in repository tests.
    from people_gator_api.schemas.common import VersionedTarget
    versions = {source.object_id: source.version for source in patch.sources}
    return patch.model_copy(update={"sources": [VersionedTarget(object_id=identity, version=versions.get(identity, 1)) for identity in source_ids]})
