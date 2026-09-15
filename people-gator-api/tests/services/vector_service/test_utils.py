from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import sys
import types
import uuid
from pathlib import Path

import pytest


repo_root = Path(__file__).resolve().parents[3]
module_path = repo_root / "src/people_gator_api/services/weaviate_service/utils.py"
package_name = "people_gator_api.services.weaviate_service"

if package_name not in sys.modules:
    package_module = types.ModuleType(package_name)
    package_module.__path__ = [str(module_path.parent)]
    sys.modules[package_name] = package_module

spec = importlib.util.spec_from_file_location(f"{package_name}.utils_under_test", module_path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
face_response = module.face_response
source_response = module.source_response


@dataclass
class FakeLinkedObject:
    uuid: uuid.UUID


@dataclass
class FakeReference:
    objects: list[FakeLinkedObject]


def test_face_response_raises_clear_error_for_empty_reference_links() -> None:
    references = {
        "principal": FakeReference([]),
        "entity": FakeReference([]),
        "source": FakeReference([]),
    }

    with pytest.raises(KeyError, match="has no linked objects"):
        face_response(
            {
                "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
                "keypoints": [],
                "confidence": 0.8,
            },
            references,
            uuid.uuid4(),
        )


def test_optional_json_dict_decodes_nested_json_objects() -> None:
    metadata = module.optional_json_dict(
        {"metadata": '{"foo": {"bar": 1}, "baz": [true, null]}'},
        "metadata",
    )

    assert metadata == {"foo": {"bar": 1}, "baz": [True, None]}


def test_source_response_reconstructs_page_metadata_from_flat_properties() -> None:
    document_id = uuid.uuid4()
    page_id = uuid.uuid4()
    uri = f"https://www.digitalniknihovna.cz/mzk/view/uuid:{document_id}?page=uuid:{page_id}"

    response = source_response(
        {
            "source_type": "page",
            "uri": uri,
            "library": "mzk",
            "document": document_id,
            "page": page_id,
        },
        {},
        uuid.uuid4(),
    )

    assert response.metadata is not None
    assert response.metadata.library == "mzk"
    assert response.metadata.document == document_id
    assert response.metadata.page == page_id
    assert str(response.metadata.kramerius_url) == uri


def test_optional_alias_text_array_accepts_text_array() -> None:
    aliases = module.optional_alias_text_array(
        {"aliases": ["Zoltan Mihaly Nagy", "Zoltan Nagy"]},
        "aliases",
    )

    assert aliases == ["Zoltan Mihaly Nagy", "Zoltan Nagy"]


def test_optional_alias_text_array_rejects_non_string_items() -> None:
    with pytest.raises(TypeError, match="contains a non-string alias item"):
        module.optional_alias_text_array(
            {"aliases": [{"alias": "Zoltan Mihaly Nagy"}]},
            "aliases",
        )


@pytest.mark.asyncio
async def test_fetch_collection_page_with_total_count_skips_object_fetch_for_zero_limit() -> None:
    class _Query:
        async def fetch_objects(self, **_kwargs: object) -> types.SimpleNamespace:
            raise AssertionError("fetch_objects should not be called when limit is zero")

    class _Aggregate:
        async def over_all(self, **_kwargs: object) -> types.SimpleNamespace:
            return types.SimpleNamespace(total_count=17)

    class _Collection:
        query = _Query()
        aggregate = _Aggregate()

    class _Collections:
        @staticmethod
        def get(name: str) -> _Collection:
            del name
            return _Collection()

    client = types.SimpleNamespace(collections=_Collections())

    objects, total_count = await module.fetch_collection_page_with_total_count(
        client,  # type: ignore[reportArgumentType] - test double for WeaviateAsyncClient
        collection_name="ignored",
        filters=None,
        limit=0,
        return_references=[],
        after_id=None,
    )

    assert objects == []
    assert total_count == 17
