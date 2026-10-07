import io
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import AnyUrl

from people_gator_api.media import page_image, page_layout
from people_gator_api.routes.v1.media import router
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import PageResponse, page_url
from people_gator_api.services.auth_service import get_current_user
from people_gator_api.services.database_service import get_database
from people_gator_api.settings import (
    LocalStorageSettings,
    PageImageCacheSettings,
    StorageSettings,
    settings,
)


@pytest.fixture
def page() -> PageResponse:
    document_id, page_id = uuid.uuid4(), uuid.uuid4()
    return PageResponse(
        source_id=uuid.uuid4(),
        source_type=SourceKind.page,
        url=AnyUrl(page_url("mzk", document_id, page_id)),
        library="mzk",
        document_id=document_id,
        page_id=page_id,
    )


@pytest.fixture
def client(
    page: PageResponse, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "storage", StorageSettings(
        local=LocalStorageSettings(root=tmp_path),
    ))
    monkeypatch.setattr(settings, "page_image_cache", PageImageCacheSettings(
        widths=[64, 128],
    ))
    async def get_page(source_id: uuid.UUID) -> PageResponse | None:
        return page if source_id == page.source_id else None

    database = SimpleNamespace(sources=SimpleNamespace(
        get_page=AsyncMock(side_effect=get_page),
    ))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: database
    app.dependency_overrides[get_current_user] = lambda: object()
    with TestClient(app) as test_client:
        yield test_client


def _image(color: str, format: str = "PNG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (160, 80), color).save(buffer, format=format)
    return buffer.getvalue()


def test_page_upload_contracts_require_ingest_scope() -> None:
    app = FastAPI()
    app.include_router(router)
    paths = app.openapi()["paths"]
    for resource in ("image", "page-layout"):
        operation = paths[f"/pages/{{page_source_id}}/{resource}"]["put"]
        assert any(
            "people-gator:ingest" in scopes
            for item in operation["security"] for scopes in item.values()
        )
        content_type = "multipart/form-data" if resource == "image" else "application/json"
        assert content_type in operation["requestBody"]["content"]
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/FileUploadResponse"
        }


def test_image_upload_creates_and_replaces_original_and_derivatives(
    client: TestClient, page: PageResponse,
) -> None:
    url = f"/pages/{page.source_id}/image"
    assert client.get(url).status_code == 404
    for color, format in (("red", "PNG"), ("blue", "JPEG")):
        uploaded = _image(color, format)
        before_upload = datetime.now(UTC)
        response = client.put(url, files={"file": (f"scan.{format.lower()}", uploaded)})
        after_upload = datetime.now(UTC)
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["source_id"] == str(page.source_id)
        assert receipt["media_type"] == "image/jpeg"
        uploaded_at = datetime.fromisoformat(receipt["uploaded_at"])
        assert uploaded_at.utcoffset() == UTC.utcoffset(uploaded_at)
        assert before_upload <= uploaded_at <= after_upload
        original = client.get(url)
        assert original.headers["content-type"] == "image/jpeg"
        assert receipt["size_bytes"] == len(original.content)
        if format == "JPEG":
            assert original.content == uploaded
        else:
            assert receipt["size_bytes"] != len(uploaded)
        for width in (None, 64, 128):
            fetched = client.get(url, params={} if width is None else {"width": width})
            assert fetched.status_code == 200
            with Image.open(io.BytesIO(fetched.content)) as image:
                assert image.format == "JPEG"
                assert image.size == (width or 160, (width or 160) // 2)
                red, _, blue = cast(tuple[int, int, int], image.convert("RGB").getpixel((0, 0)))
                assert red > blue if color == "red" else blue > red


def test_invalid_image_upload_preserves_existing_scan(
    client: TestClient, page: PageResponse,
) -> None:
    url = f"/pages/{page.source_id}/image"
    assert client.put(url, files={"file": ("scan.png", _image("red"))}).status_code == 200
    original = client.get(url).content
    for content in (b"", b"not an image"):
        response = client.put(url, files={"file": ("scan.jpg", content, "image/jpeg")})
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_image"
        assert client.get(url).content == original
    assert client.put(url).status_code == 422


def test_layout_upload_creates_and_replaces_layout(
    client: TestClient, page: PageResponse, tmp_path: Path,
) -> None:
    url = f"/pages/{page.source_id}/page-layout"
    assert client.get(url).status_code == 404
    for layout_id in ("first", "Žluťoučký replacement"):
        payload: dict[str, object] = {"id": layout_id, "page_size": [160, 80], "regions": [], "reading_order": {}}
        before_upload = datetime.now(UTC)
        response = client.put(url, json=payload)
        after_upload = datetime.now(UTC)
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["source_id"] == str(page.source_id)
        assert receipt["media_type"] == "application/json"
        uploaded_at = datetime.fromisoformat(receipt["uploaded_at"])
        assert uploaded_at.utcoffset() == UTC.utcoffset(uploaded_at)
        assert before_upload <= uploaded_at <= after_upload
        key = page_layout.page_layout_key(page.library, page.document_id, page.page_id)
        stored_bytes = (tmp_path / key).read_bytes()
        assert receipt["size_bytes"] == len(stored_bytes)
        if layout_id != "first":
            assert receipt["size_bytes"] > len(stored_bytes.decode("utf-8"))
        assert client.get(url).json() == payload
    assert client.put(url, json={"id": "invalid"}).status_code == 422
    assert client.get(url).json()["id"] == "Žluťoučký replacement"


@pytest.mark.parametrize("resource", ["image", "page-layout"])
def test_upload_requires_existing_page(client: TestClient, resource: str) -> None:
    url = f"/pages/{uuid.uuid4()}/{resource}"
    if resource == "image":
        response = client.put(url, files={"file": ("scan.png", _image("red"))})
    else:
        response = client.put(url, json={"id": "layout", "page_size": [160, 80], "regions": [], "reading_order": {}})
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "not_found"


@pytest.mark.parametrize("resource", ["image", "page-layout"])
def test_upload_translates_storage_errors(
    client: TestClient, page: PageResponse, resource: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = f"/pages/{page.source_id}/{resource}"
    failure = AsyncMock(side_effect=OSError("storage unavailable"))
    if resource == "image":
        monkeypatch.setattr(page_image, "write_bytes", failure)
        response = client.put(url, files={"file": ("scan.png", _image("red"))})
    else:
        monkeypatch.setattr(page_layout, "open_file", Mock(side_effect=OSError("storage unavailable")))
        response = client.put(url, json={"id": "layout", "page_size": [160, 80], "regions": [], "reading_order": {}})
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "storage_error"
