from __future__ import annotations

import os
import uuid

os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__OPENROUTER__API_KEY", "test")

from typing import Literal

import asyncio

import pytest
from botocore.exceptions import ClientError

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.pero import (
    PageLayoutModel,
    RegionLayoutModel,
    TextLineModel,
)
from people_gator_api.schemas.sources import (
    PageSourceMetadata,
    SourceRecord,
    SourceResponse,
)
from people_gator_api.services.crud_services import page_layout_service
from people_gator_api.settings import PageLayoutSettings


def _page_source() -> SourceResponse:
    return SourceRecord(
        source_id=uuid.uuid4(),
        source_type=SourceKind.page,
        uri="https://www.digitalniknihovna.cz/mzk/view/uuid:x?page=uuid:y",
        metadata=PageSourceMetadata(
            library="mzk",
            document=uuid.uuid4(),
            page=uuid.uuid4(),
        ),
    )


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
    """Minimal double for :class:`_S3FileContext` keyed by (key, mode)."""

    store: dict[str, str] = {}

    def __init__(self, key: str, mode: Literal["r", "w"]) -> None:
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
        return self  # pyright: ignore[reportReturnType] - test double

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

    def fake_open_file(
        path: str, mode: Literal["r", "w"]
    ) -> _FakeS3Context:
        return _FakeS3Context(path, mode)

    monkeypatch.setattr(page_layout_service, "open_file", fake_open_file)


def _install_source_lookup(
    monkeypatch: pytest.MonkeyPatch, source: SourceResponse
) -> None:
    async def fake_resolve(
        _client: object,
        *,
        source_id: uuid.UUID | None,
        page_path: str | None,
    ) -> SourceResponse:
        del source_id, page_path
        return source

    monkeypatch.setattr(
        page_layout_service, "resolve_page_source", fake_resolve
    )


@pytest.mark.asyncio
async def test_put_page_layout_stores_canonical_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _page_source()
    _install_source_lookup(monkeypatch, source)
    _install_fake_s3(monkeypatch)
    monkeypatch.setattr(
        page_layout_service.settings,
        "page_layout",
        PageLayoutSettings(key_prefix="ocr/page-layouts"),
    )
    client = object()  # pyright: ignore[reportAssignmentType] - lookup is mocked

    expected_key = (
        f"ocr/page-layouts/{source.metadata.library}"  # pyright: ignore[reportOptionalMemberAccess]
        f"/{source.metadata.document}"  # pyright: ignore[reportOptionalMemberAccess]
        f"/{source.metadata.page}.json"  # pyright: ignore[reportOptionalMemberAccess]
    )
    layout = _layout()
    stored = await page_layout_service.put_page_layout(
        client,  # pyright: ignore[reportArgumentType] - lookup is mocked
        source_id=uuid.uuid4(),
        page_path=None,
        layout=layout,
    )

    assert stored == layout
    assert expected_key in _FakeS3Context.store
    # Stored document round-trips through the strict schema.
    reloaded = PageLayoutModel.model_validate_json(
        _FakeS3Context.store[expected_key]
    )
    assert reloaded == layout


@pytest.mark.asyncio
async def test_get_page_layout_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _page_source()
    _install_source_lookup(monkeypatch, source)
    _install_fake_s3(monkeypatch)
    client = object()  # pyright: ignore[reportAssignmentType] - lookup is mocked

    await page_layout_service.put_page_layout(
        client,  # pyright: ignore[reportArgumentType] - lookup is mocked
        source_id=None,
        page_path=f"mzk/{source.metadata.page}",  # pyright: ignore[reportOptionalMemberAccess]
        layout=_layout(),
    )

    fetched = await page_layout_service.get_page_layout(
        client,  # pyright: ignore[reportArgumentType] - lookup is mocked
        source_id=None,
        page_path="mzk/whatever",
    )
    assert fetched.id == "page-1"
    assert fetched.regions[0].lines[0].transcription == "hello"


@pytest.mark.asyncio
async def test_get_page_layout_missing_returns_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _page_source()
    _install_source_lookup(monkeypatch, source)
    _install_fake_s3(monkeypatch)

    with pytest.raises(page_layout_service.SourceResolutionError) as exc_info:
        await page_layout_service.get_page_layout(
            object(),  # pyright: ignore[reportArgumentType] - lookup is mocked
            source_id=None,
            page_path="mzk/whatever",
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


@pytest.mark.asyncio
async def test_rejects_non_page_source(monkeypatch: pytest.MonkeyPatch) -> None:
    image_source = SourceRecord(
        source_id=uuid.uuid4(),
        source_type=SourceKind.image,
        uri="https://example.test/image.jpg",
        metadata=None,
    )
    _install_source_lookup(monkeypatch, image_source)

    with pytest.raises(page_layout_service.SourceResolutionError) as exc_info:
        await page_layout_service.page_layout_key(image_source)

    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_page_layout_source"


def test_rejects_both_selectors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_s3(monkeypatch)

    async def _run() -> None:
        await page_layout_service.resolve_page_source(
            object(),  # pyright: ignore[reportArgumentType] - rejected before use
            source_id=uuid.uuid4(),
            page_path="mzk/some-page",
        )

    with pytest.raises(page_layout_service.SourceResolutionError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_page_layout_selector"


def test_rejects_missing_selector(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_s3(monkeypatch)

    async def _run() -> None:
        await page_layout_service.resolve_page_source(
            object(),  # pyright: ignore[reportArgumentType] - rejected before use
            source_id=None,
            page_path=None,
        )

    with pytest.raises(page_layout_service.SourceResolutionError) as exc_info:
        asyncio.run(_run())
    assert exc_info.value.status_code == 422
    assert exc_info.value.code == "invalid_page_layout_selector"
