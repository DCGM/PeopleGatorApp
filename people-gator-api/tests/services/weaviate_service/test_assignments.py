from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from people_gator_api.schemas.enums import AssignmentType
from people_gator_api.services.weaviate_service.assignments import (
    assigned_reference_ids,
    source_has_assignment,
)
from people_gator_api.services.weaviate_service.db_schema import (
    FACE_COLLECTION,
    TEXT_MENTION_COLLECTION,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("assignment", "expected_collection"),
    [
        (AssignmentType.face, FACE_COLLECTION),
        (AssignmentType.text_mention, TEXT_MENTION_COLLECTION),
    ],
)
async def test_assigned_reference_ids_uses_requested_annotation_kind(
    assignment: AssignmentType,
    expected_collection: str,
) -> None:
    first_id = uuid.uuid4()
    second_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class _Query:
        async def fetch_objects(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        uuid=uuid.uuid4(),
                        references={
                            "entity": SimpleNamespace(
                                objects=[
                                    SimpleNamespace(uuid=first_id),
                                    SimpleNamespace(uuid=second_id),
                                ]
                            )
                        },
                    )
                ]
            )

    class _Collections:
        def get(self, collection_name: str) -> SimpleNamespace:
            assert collection_name == expected_collection
            return SimpleNamespace(query=_Query())

    result = await assigned_reference_ids(
        SimpleNamespace(collections=_Collections()),  # pyright: ignore[reportArgumentType]
        assignment,
        "entity",
    )

    assert result == {first_id, second_id}
    assert "link_on='entity'" in repr(captured["filters"])
    assert "GREATER_THAN" in repr(captured["filters"])


@pytest.mark.asyncio
async def test_source_has_assignment_requires_source_and_entity_references() -> None:
    source_id = uuid.uuid4()
    captured: dict[str, object] = {}

    class _Query:
        async def fetch_objects(self, **kwargs: object) -> SimpleNamespace:
            captured.update(kwargs)
            return SimpleNamespace(objects=[SimpleNamespace(uuid=uuid.uuid4())])

    collections = SimpleNamespace(
        get=lambda collection_name: SimpleNamespace(query=_Query())
    )
    result = await source_has_assignment(
        SimpleNamespace(collections=collections),  # pyright: ignore[reportArgumentType]
        source_id,
        AssignmentType.face,
    )

    assert result is True
    conditions = vars(captured["filters"])["filters"]
    assert "link_on='entity'" in repr(conditions[0])
    assert "link_on='source'" in repr(conditions[1])
    assert str(source_id) in repr(conditions[1])
