"""Errors shared by persistence-independent media services."""


class SourceResolutionError(ValueError):
    """A media selector or stored object could not be resolved."""

    def __init__(self, message: str, *, status_code: int, code: str) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
