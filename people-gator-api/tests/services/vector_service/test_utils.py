from __future__ import annotations

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


class FakeLinkedObject:
    def __init__(self, object_uuid: uuid.UUID) -> None:
        self.uuid = object_uuid


class FakeReference:
    def __init__(self, objects: list[FakeLinkedObject]) -> None:
        self.objects = objects


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
