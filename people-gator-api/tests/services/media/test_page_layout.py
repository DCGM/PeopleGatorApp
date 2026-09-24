from __future__ import annotations

import os
import uuid
from typing import Literal

import pytest
from botocore.exceptions import ClientError

os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")

from people_gator_api.schemas.pero import (
    PageLayoutModel,
    RegionLayoutModel,
    TextLineModel,
)
from people_gator_api.media import page_layout
from people_gator_api.settings import PageLayoutSettings


_LIBRARY = "mzk"
_DOCUMENT_ID = uuid.UUID("1fa8a1a1-b4f5-47d9-91a8-c9cc64677b46")
_PAGE_ID = uuid.UUID("0b7cd05f-ca4c-41d2-81a8-6b46742a4d23")


def _layout() -> PageLayoutModel:
    line = TextLineModel(
        id="line-1",
        baseline=[[0.0, 10.0], [100.0, 10.0]],
        polygon=[[0.0, 0.0], [100.0, 0.0], [100.0, 20.0], [0.0, 20.0]],
        heights=[10.0],
        transcription="hello",
        transcription_confidence=0.99,
        index=0,
    )
    region = RegionLayoutModel(
        id="region-1",
        polygon=[[0.0, 0.0], [100.0, 0.0], [100.0, 40.0], [0.0, 40.0]],
        region_type="paragraph",
        transcription="hello",
        lines=[line],
    )
    return PageLayoutModel(
        id="page-1",
        page_size=(1000, 2000),
        regions=[region],
        reading_order={"region-1": 0},
    )


class _FakeS3Context:
    store: dict[str, str] = {}

    def __init__(self, key: str, mode: Literal["r", "w"]) -> None:
        super().__init__()
        self._key = key
        self._mode = mode
        self._buffer = ""

    async def __aenter__(self) -> "_FakeS3Context":
        if self._mode == "r" and self._key not in self.store:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
                "GetObject",
            )
        self._buffer = self.store.get(self._key, "")
        return self

    async def __aexit__(self, *_args: object) -> None:
        if self._mode == "w":
            self.store[self._key] = self._buffer

    def read(self) -> str:
        return self._buffer

    def write(self, data: str) -> int:
        self._buffer = data
        return len(data)


def _install_fake_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeS3Context.store = {}

    def fake_open_file(path: str, mode: Literal["r", "w"]) -> _FakeS3Context:
        return _FakeS3Context(path, mode)

    monkeypatch.setattr(page_layout, "open_file", fake_open_file)


@pytest.mark.asyncio
async def test_put_page_layout_stores_canonical_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_s3(monkeypatch)
    monkeypatch.setattr(
        page_layout.settings,
        "page_layout",
        PageLayoutSettings(key_prefix="ocr/page-layouts"),
    )
    layout = _layout()

    stored = await page_layout.put_page_layout(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID, layout
    )

    expected_key = f"ocr/page-layouts/{_LIBRARY}/{_DOCUMENT_ID}/{_PAGE_ID}.json"
    assert stored == layout
    assert PageLayoutModel.model_validate_json(_FakeS3Context.store[expected_key]) == layout


@pytest.mark.asyncio
async def test_get_page_layout_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_s3(monkeypatch)
    await page_layout.put_page_layout(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID, _layout()
    )

    fetched = await page_layout.get_page_layout(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID
    )

    assert fetched.id == "page-1"
    assert fetched.regions[0].lines[0].transcription == "hello"


@pytest.mark.asyncio
async def test_get_page_layout_missing_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_s3(monkeypatch)

    with pytest.raises(page_layout.SourceResolutionError) as exc_info:
        await page_layout.get_page_layout(
            _LIBRARY, _DOCUMENT_ID, _PAGE_ID
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


def test_page_layout_key_needs_no_persistence_object() -> None:
    assert page_layout.page_layout_key(
        _LIBRARY, _DOCUMENT_ID, _PAGE_ID
    ) == f"page-layouts/{_LIBRARY}/{_DOCUMENT_ID}/{_PAGE_ID}.json"
