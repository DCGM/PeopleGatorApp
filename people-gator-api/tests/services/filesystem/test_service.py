import asyncio
import io
import json
import os
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pydantic import ValidationError

from people_gator_api.filesystem import LocalFilesystem, S3Filesystem
from people_gator_api.media import image_content, page_image, page_layout
from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.services import filesystem_service
from people_gator_api.services.filesystem_service import FilesystemDependency, get_filesystem
from people_gator_api.settings import (
    FilesystemBaseSetting, LocalStorageSettings, Settings, StorageSettings, settings,
)


S3 = {
    "access_key_id": "test", "secret_access_key": "test",
    "bucket_name": "bucket", "region": "eu-central-1",
}
POSTGRES = {
    "host": "localhost", "port": 5432, "user": "test",
    "password": "test", "database": "test",
}


@pytest.fixture
def local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalFilesystem:
    monkeypatch.setattr(settings, "storage", StorageSettings(
        local=LocalStorageSettings(root=tmp_path),
    ))
    filesystem = get_filesystem()
    assert isinstance(filesystem, LocalFilesystem)
    return filesystem


@pytest.mark.parametrize("backend,connection", [("s3", S3), ("local", {})])
@pytest.mark.parametrize("explicit_null", [False, True], ids=["omitted", "null"])
def test_non_null_configuration_selects_backend(
    backend: str, connection: dict[str, Any], explicit_null: bool,
) -> None:
    other = "local" if backend == "s3" else "s3"
    data: dict[str, Any] = {backend: connection}
    if explicit_null:
        data[other] = None
    config = StorageSettings.model_validate(data)
    assert config.backend == backend
    assert getattr(config, other) is None
    selected = getattr(config, backend)
    assert isinstance(selected, FilesystemBaseSetting)
    assert "enabled" not in selected.model_dump()
    if backend == "local":
        assert selected.root == Path("./storage")
    assert StorageSettings.model_validate_json(config.model_dump_json()) == config


@pytest.mark.parametrize("data", [
    {}, {"s3": None}, {"local": None},
    {"s3": None, "local": None}, {"s3": S3, "local": {}},
], ids=["omitted", "s3-null", "local-null", "both-null", "both-set"])
def test_requires_exactly_one_backend(data: dict[str, Any]) -> None:
    with pytest.raises(ValidationError, match="Exactly one filesystem backend must be set"):
        StorageSettings.model_validate(data)


def test_s3_requires_connection_fields() -> None:
    with pytest.raises(ValidationError) as empty:
        StorageSettings.model_validate({"s3": {}})
    assert all(error["type"] == "missing" for error in empty.value.errors())
    for field in S3:
        incomplete = {key: value for key, value in S3.items() if key != field}
        with pytest.raises(ValidationError) as missing:
            StorageSettings.model_validate({"s3": incomplete})
        assert missing.value.errors()[0]["loc"] == ("s3", field)
        assert missing.value.errors()[0]["type"] == "missing"


def test_backend_selector_is_not_a_configuration_field() -> None:
    with pytest.raises(ValidationError) as invalid:
        StorageSettings.model_validate({"local": {}, "backend": "s3"})
    assert invalid.value.errors()[0]["type"] == "extra_forbidden"
    assert invalid.value.errors()[0]["loc"] == ("backend",)


@pytest.fixture
def clean_settings_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__"):
            monkeypatch.delenv(name)


@pytest.mark.usefixtures("clean_settings_environment")
@pytest.mark.parametrize("backend", ["s3", "local"])
@pytest.mark.parametrize("source", ["nested", "json"])
def test_environment_selects_non_null_backend(
    backend: str, source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = "local" if backend == "s3" else "s3"
    connection = S3 if backend == "s3" else {"root": str(tmp_path)}
    if source == "json":
        monkeypatch.setenv("PEOPLE_GATOR_API__STORAGE", json.dumps({backend: connection, other: None}))
    else:
        for name, value in connection.items():
            monkeypatch.setenv(f"PEOPLE_GATOR_API__STORAGE__{backend.upper()}__{name.upper()}", value)
    configured = Settings(_env_file=None, persistence={"postgres": POSTGRES})
    assert configured.storage.backend == backend
    assert getattr(configured.storage, other) is None
    if backend == "local":
        assert configured.storage.local.root == tmp_path
    else:
        assert configured.storage.s3.model_dump(include=set(S3)) == S3


@pytest.mark.usefixtures("clean_settings_environment")
def test_environment_rejects_two_configured_backends(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in S3.items():
        monkeypatch.setenv(f"PEOPLE_GATOR_API__STORAGE__S3__{name.upper()}", value)
    monkeypatch.setenv("PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT", str(tmp_path))
    with pytest.raises(ValidationError, match="Exactly one filesystem backend must be set"):
        Settings(_env_file=None, persistence={"postgres": POSTGRES})


def test_provider_tracks_backend_changes(local_storage: LocalFilesystem, monkeypatch: pytest.MonkeyPatch) -> None:
    s3_config = StorageSettings.model_validate({"s3": {
        "access_key_id": "test", "secret_access_key": "test",
        "bucket_name": "selected-bucket", "region": "eu-central-1",
    }})
    monkeypatch.setattr(settings, "storage", s3_config)
    filesystem = get_filesystem()
    assert isinstance(filesystem, S3Filesystem)
    assert filesystem.config.bucket_name == "selected-bucket"


@pytest.mark.asyncio
async def test_configured_helpers(local_storage: LocalFilesystem) -> None:
    await filesystem_service.write_bytes("data/file.bin", b"hello")
    assert await filesystem_service.read_bytes("data/file.bin") == b"hello"
    async with filesystem_service.open_file("data/text.txt", "w") as file:
        file.write("Žluťoučký")
    async with filesystem_service.open_file("data/text.txt", "r") as file:
        assert file.read() == "Žluťoučký"
    assert [entry.key for entry in await filesystem_service.lsdir("data/")] == [
        "data/file.bin", "data/text.txt",
    ]
    assert [entry.key for entry in await filesystem_service.glob("data/*.bin")] == ["data/file.bin"]


def test_fastapi_dependency_and_override(local_storage: LocalFilesystem, tmp_path: Path) -> None:
    app = FastAPI()

    @app.get("/backend")
    async def backend(filesystem: FilesystemDependency) -> dict[str, str]:
        return {"backend": type(filesystem).__name__, "data": (await filesystem.read_bytes("value.txt")).decode()}

    asyncio.run(local_storage.write_bytes("value.txt", b"configured"))
    with TestClient(app) as client:
        assert client.get("/backend").json() == {"backend": "LocalFilesystem", "data": "configured"}
        override = LocalFilesystem(tmp_path / "override")
        asyncio.run(override.write_bytes("value.txt", b"overridden"))
        app.dependency_overrides[get_filesystem] = lambda: override
        assert client.get("/backend").json()["data"] == "overridden"


@pytest.mark.asyncio
async def test_local_media_reads_and_missing_objects(local_storage: LocalFilesystem) -> None:
    url = "https://example.org/sample.png"
    await local_storage.write_bytes(image_content.image_content_key(url), b"image-content")
    assert await image_content.get_image_content(url) == (b"image-content", "image/png")
    with pytest.raises(SourceResolutionError) as missing:
        await image_content.get_image_content("https://example.org/missing.png")
    assert missing.value.status_code == 404
    document_id, page_id = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(SourceResolutionError) as missing:
        await page_layout.get_page_layout("library", document_id, page_id)
    assert missing.value.status_code == 404
    with pytest.raises(SourceResolutionError) as missing:
        await page_image.get_page_image("library", document_id, page_id)
    assert missing.value.status_code == 404


@pytest.mark.asyncio
async def test_local_page_image_cache(local_storage: LocalFilesystem) -> None:
    document_id, page_id = uuid.uuid4(), uuid.uuid4()
    image = io.BytesIO()
    Image.new("RGB", (400, 200)).save(image, "JPEG")
    await local_storage.write_bytes(page_image.page_image_key("library", document_id, page_id), image.getvalue())
    first = await page_image.get_page_image("library", document_id, page_id, max_width=256)
    assert first.cache_hit is False
    pending = list(page_image._background_cache_writes)
    if pending:
        await asyncio.gather(*pending)
    second = await page_image.get_page_image("library", document_id, page_id, max_width=256)
    assert second.cache_hit is True
    assert second.content == first.content
