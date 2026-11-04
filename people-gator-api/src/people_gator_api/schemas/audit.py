"""Optimistic concurrency failures shared by persistence adapters."""


class VersionConflict(Exception):
    """The caller must reload the object before attempting another edit."""
