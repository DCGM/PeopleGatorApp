import asyncio
import io
import os
import uuid
from pathlib import Path

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


@pytest.fixture
def local_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalFilesystem:
    monkeypatch.setattr(settings, "storage", StorageSettings(
        local=LocalStorageSettings(enabled=True, root=tmp_path),
    ))
    filesystem = get_filesystem()
    assert isinstance(filesystem, LocalFilesystem)
    return filesystem


def test_backend_validation_and_default() -> None:
    config = StorageSettings(s3={
        "access_key_id": "test", "secret_access_key": "test",
        "bucket_name": "bucket", "region": "eu-central-1",
    })
    assert config.backend == "s3"
    assert StorageSettings(local={"enabled": True}).s3 is None
    with pytest.raises(ValidationError, match="Exactly one filesystem backend"):
        StorageSettings()
    with pytest.raises(ValidationError):
        StorageSettings.model_validate({"backend": "invalid"})


@pytest.mark.parametrize("s3_enabled,local_enabled", [(False, False), (True, True)])
def test_requires_exactly_one_enabled_backend(s3_enabled: bool, local_enabled: bool) -> None:
    with pytest.raises(ValidationError, match="Exactly one filesystem backend"):
        StorageSettings(s3={
            "enabled": s3_enabled,
            "access_key_id": "test", "secret_access_key": "test",
            "bucket_name": "bucket", "region": "eu-central-1",
        }, local={"enabled": local_enabled})


def test_local_backend_with_disabled_s3() -> None:
    config = StorageSettings(s3={
        "enabled": False,
        "access_key_id": "test", "secret_access_key": "test",
        "bucket_name": "bucket", "region": "eu-central-1",
    }, local={"enabled": True})
    assert config.backend == "local"
    assert isinstance(config.local, FilesystemBaseSetting)
    assert isinstance(config.s3, FilesystemBaseSetting)


def test_local_environment_settings_without_s3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.startswith("PEOPLE_GATOR_API__STORAGE"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PEOPLE_GATOR_API__STORAGE__LOCAL__ENABLED", "true")
    monkeypatch.setenv("PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT", str(tmp_path))
    other_settings = settings.model_dump(exclude={"storage"})
    configured = Settings(_env_file=None, **other_settings)
    assert configured.storage.backend == "local"
    assert configured.storage.local.root == tmp_path
    assert configured.storage.s3 is None


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
