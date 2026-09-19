from pydantic import BaseModel

from people_gator_api.schemas.enums import Language


class TranslationRequest(BaseModel):
    text: str
    language: Language
    """Target language to translate ``text`` into."""


class TranslationResponse(BaseModel):
    text: str
    translation: str
    source_language: Language
    target_language: Language
