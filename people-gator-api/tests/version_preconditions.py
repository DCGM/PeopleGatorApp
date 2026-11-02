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
