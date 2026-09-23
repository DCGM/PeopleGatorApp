from typing import Any, cast

import pytest
from pydantic import TypeAdapter, ValidationError

from people_gator_api.batch_settings import BatchSettings, batch_settings
from people_gator_api.schemas.entities import (
    MAX_ENTITY_BATCH_SIZE,
    EntityBatchCreateRequest,
)
from people_gator_api.schemas.faces import (
    MAX_FACE_BATCH_SIZE,
    FacesBatchCreateRequest,
)
from people_gator_api.schemas.mentions import (
    MAX_TEXT_MENTION_BATCH_SIZE,
    TextMentionsBatchCreateRequest,
)
from people_gator_api.schemas.sources import (
    MAX_MEDIA_BATCH_SIZE,
    PageBatchCreateRequest,
)


def _max_items(annotation: Any) -> int:
    return cast(int, TypeAdapter(annotation).json_schema()["maxItems"])


def test_batch_schema_limits_come_from_settings() -> None:
    assert MAX_ENTITY_BATCH_SIZE == batch_settings.max_entity_batch_size
    assert MAX_FACE_BATCH_SIZE == batch_settings.max_face_batch_size
    assert (
        MAX_TEXT_MENTION_BATCH_SIZE
        == batch_settings.max_text_mention_batch_size
    )
    assert MAX_MEDIA_BATCH_SIZE == batch_settings.max_media_batch_size

    assert _max_items(EntityBatchCreateRequest) == MAX_ENTITY_BATCH_SIZE
    assert _max_items(FacesBatchCreateRequest) == MAX_FACE_BATCH_SIZE
    assert (
        _max_items(TextMentionsBatchCreateRequest)
        == MAX_TEXT_MENTION_BATCH_SIZE
    )
    assert _max_items(PageBatchCreateRequest) == MAX_MEDIA_BATCH_SIZE


def test_batch_settings_support_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "PEOPLE_GATOR_API__BATCH__MAX_ENTITY_BATCH_SIZE", "37"
    )

    configured = BatchSettings()

    assert configured.max_entity_batch_size == 37


def test_batch_settings_require_positive_sizes() -> None:
    with pytest.raises(ValidationError):
        BatchSettings(max_media_batch_size=0)
