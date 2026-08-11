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
