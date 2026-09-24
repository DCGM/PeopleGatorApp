"""Language values shared by settings and API schemas without import cycles."""

from enum import StrEnum


class Language(StrEnum):
    """Languages supported by the translation endpoint."""

    czech = "cs"
    english = "en"
    german = "de"
