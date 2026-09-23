from pydantic import BaseModel, Field

from people_gator_api.schemas.enums import Language


class TranslationRequest(BaseModel):
    """Request schema for translating text into a target language."""
    text: str = Field(description="The text to be translated.")
    language: Language = Field(description="Target language to translate ``text`` into.")


class TranslationResponse(BaseModel):
    """Response schema for a translation request."""
    text: str = Field(description="The original text to be translated.")
    translation: str = Field(description="The translated text.")
    source_language: Language = Field(description="The language of the original text automatically detected.")
    target_language: Language = Field(description="The language into which the text was translated.")


__all__ = [
    "TranslationRequest",
    "TranslationResponse",
]
