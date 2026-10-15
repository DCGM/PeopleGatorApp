"""Real default PostgreSQL pool and S3 SDK against explicitly gated HTTP storage."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import io
from unittest.mock import AsyncMock

from aiohttp import web
from fastapi import FastAPI
import httpx
from PIL import Image
import pytest
import pytest_asyncio

from people_gator_api.filesystem.local import LocalFilesystem
from people_gator_api.media import page_image
from people_gator_api.media.page_image import page_image_key
from people_gator_api.media.page_layout import page_layout_key
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.routes.v1 import router
from people_gator_api.seeding.preview import seed_preview
from people_gator_api.services import auth_service, database_service
from people_gator_api.services.api_key_service import APIKeyRecord
from people_gator_api.settings import PageImageCacheSettings, S3Settings, StorageSettings, settings


@dataclass
class Gate:
    release: asyncio.Event = field(default_factory=asyncio.Event)
    outcome: str = "success"


@dataclass
class Storage:
    gates: dict[str, Gate] = field(default_factory=dict)
    entered: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    objects: dict[str, bytes] = field(default_factory=dict)

    async def handle(self, request):
        key = request.match_info["key"]
        data = await request.read()
        if request.method == "PUT":
            self.entered.put_nowait(key)
            gate = self.gates.get(key)
            if gate is not None:
                await gate.release.wait()
                if gate.outcome == "denied":
                    return web.Response(status=403, content_type="application/xml", text=(
                        "<Error><Code>AccessDenied</Code><Message>Controlled denial</Message></Error>"
                    ))
            self.objects[key] = data
            return web.Response(headers={"ETag": '"synthetic"'})
        if key in self.objects:
            return web.Response(body=self.objects[key])
        return web.Response(status=404, content_type="application/xml",
                            text="<Error><Code>NoSuchKey</Code></Error>")

    async def wait_for_keys(self, expected):
        seen = set()
        async with asyncio.timeout(10):
            while not expected <= seen:
                seen.add(await self.entered.get())


def key_for(page, resource):
    key = page_image_key if resource == "image" else page_layout_key
    return key(page.library, page.document_id, page.page_id)


def url_for(page, resource):
    return f"/api/v1/pages/{page.source_id}/{resource}"


def image_bytes(color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (160, 80), color).save(buffer, format="JPEG")
    return buffer.getvalue()


async def upload(client, page, resource, color="red"):
    if resource == "image":
        return await client.put(url_for(page, resource), files={
            "file": ("scan.jpg", image_bytes(color), "image/jpeg"),
        })
    return await client.put(url_for(page, resource), json={
        "id": "issue10", "page_size": [160, 80], "regions": [], "reading_order": {},
    })


async def browse_and_upload(client, page, resource):
    responses = await asyncio.wait_for(asyncio.gather(
        client.get("/api/v1/entities"),
        client.get("/api/v1/search-entities", params={"query.text": "Ada"}),
        upload(client, page, resource),
        client.get("/api/v1/health"),
    ), timeout=5)
    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["items"] and responses[1].json()["items"]
    return responses[2]


async def assert_readable(client, page, resource, receipt, storage):
    response = await client.get(url_for(page, resource))
    assert response.status_code == 200
    metadata = receipt.json()
    assert metadata["source_id"] == str(page.source_id)
    assert metadata["uploaded_at"]
    assert metadata["size_bytes"] == len(storage.objects[key_for(page, resource)])
    if resource == "image":
        assert metadata["media_type"] == "image/jpeg"
        assert response.content == image_bytes()
    else:
        assert metadata["media_type"] == "application/json"
        assert response.json()["id"] == "issue10"


@pytest_asyncio.fixture
async def upload_target(migrated_postgres, tmp_path, monkeypatch):
    engine = migrated_postgres
    sessions = database_service.make_postgres_session_factory(engine)
    async with sessions() as session:
        database = postgres_database(session)
        seeded = await seed_preview(database, LocalFilesystem(tmp_path))
        pages = [await database.sources.get_page(source_id)
                 for source_id in list(seeded.pages.values())[:16]]
    monkeypatch.setattr(database_service, "_postgres_engine", engine)
    monkeypatch.setattr(database_service, "_postgres_sessions", sessions)
    monkeypatch.setattr(settings, "page_image_cache", PageImageCacheSettings(widths=[64, 128]))
    storage = Storage()
    app = web.Application()
    app.router.add_route("*", "/issue10/{key:.*}", storage.handle)
    runner = web.AppRunner(app, access_log=None, shutdown_timeout=0.1)
    await runner.setup()
    try:
        await web.TCPSite(runner, "127.0.0.1", 0).start()
        config = S3Settings(
            access_key_id="synthetic", secret_access_key="synthetic", bucket_name="issue10",
            region="us-east-1", timeout_seconds=30,
            endpoint_url=f"http://127.0.0.1:{runner.addresses[0][1]}",
        )
        monkeypatch.setattr(settings, "storage", StorageSettings(s3=config))
        api = FastAPI()
        api.include_router(router)
        # Keep actual authentication, user/key repositories and DB scopes. Only
        # credential verification is stubbed; a synthetic actor would hide leaks.
        scopes = {"people-gator:browse", "people-gator:ingest"}
        monkeypatch.setattr(auth_service, "verify_access_token", AsyncMock(return_value={
            "sub": "reviewer", "iss": "urn:people-gator:preview-seed", "scopes": list(scopes),
        }))
        monkeypatch.setattr(auth_service, "verify_api_key", AsyncMock(return_value=(
            "issue10-test-key", APIKeyRecord(
                username="issue10-test-user", display_name="Synthetic concurrency key",
                hash="unused-verification-stub", scopes=scopes,
            ),
        )))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://test",
            headers={"Authorization": "Bearer synthetic"},
        ) as client:
            yield client, pages, storage, engine
    finally:
        for gate in storage.gates.values():
            gate.release.set()
        await runner.cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["image", "page-layout"])
@pytest.mark.parametrize("count", [14, 15])
@pytest.mark.parametrize("authentication", ["bearer", "api_key"])
async def test_stalled_uploads_release_connections_before_storage(upload_target, resource, count, authentication):
    client, pages, storage, engine = upload_target
    if authentication == "api_key":
        client.headers.pop("Authorization")
        client.headers["X-API-Key"] = "synthetic"
    keys = {key_for(page, resource) for page in pages[:count]}
    storage.gates = {key: Gate() for key in keys}
    tasks = [asyncio.create_task(upload(client, page, resource)) for page in pages[:count]]
    try:
        await storage.wait_for_keys(keys)
        assert engine.pool.checkedout() == 0, engine.pool.status()
        independent = await browse_and_upload(client, pages[15], resource)
        # Completion while these gates are held is the regression assertion.
        assert all(not task.done() for task in tasks)
        assert all(not gate.release.is_set() for gate in storage.gates.values())
        assert engine.pool.checkedout() == 0, engine.pool.status()
        await assert_readable(client, pages[15], resource, independent, storage)
    finally:
        for gate in storage.gates.values():
            gate.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=10)
    assert all(response.status_code == 200 for response in responses)
    for page, response in zip(pages, responses):
        await assert_readable(client, page, resource, response, storage)
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["image", "page-layout"])
@pytest.mark.parametrize("outcome", ["denied", "timeout"])
async def test_slow_storage_failure_is_confined_and_recovers(upload_target, resource, outcome):
    client, pages, storage, engine = upload_target
    page = pages[0]
    key = key_for(page, resource)
    gate = storage.gates[key] = Gate(outcome=outcome)
    # Exercise actual SDK read timeouts/retries, without mocking an exception.
    settings.storage.s3.timeout_seconds = 1 if outcome == "timeout" else 30
    task = asyncio.create_task(upload(client, page, resource))
    try:
        await storage.wait_for_keys({key})
        assert engine.pool.checkedout() == 0
        await browse_and_upload(client, pages[15], resource)
        assert not gate.release.is_set()
        assert not task.done()
        if outcome == "denied":
            gate.release.set()
        response = await asyncio.wait_for(asyncio.shield(task), timeout=10)
        assert response.status_code == 502
        assert response.json()["detail"]["code"] == "storage_error"
        assert engine.pool.checkedout() == 0
    finally:
        gate.release.set()
        await asyncio.gather(task, return_exceptions=True)
    del storage.gates[key]
    response = await upload(client, page, resource)
    assert response.status_code == 200
    await assert_readable(client, page, resource, response, storage)
    await browse_and_upload(client, pages[15], resource)
    assert engine.pool.checkedout() == 0


@pytest.mark.asyncio
async def test_same_page_waiters_release_connections_and_keep_image_order(upload_target, monkeypatch):
    client, pages, storage, engine = upload_target
    page = pages[0]
    key = key_for(page, "image")
    gate = storage.gates[key] = Gate()
    original_lock = page_image._page_lock
    waiting = asyncio.Event()
    attempts = 0

    @asynccontextmanager
    async def tracked_lock(lock_key):
        nonlocal attempts
        if lock_key == key:
            attempts += 1
            if attempts == 31:
                waiting.set()
        async with original_lock(lock_key):
            yield

    monkeypatch.setattr(page_image, "_page_lock", tracked_lock)
    first = asyncio.create_task(upload(client, page, "image"))
    tasks = [first]
    try:
        await storage.wait_for_keys({key})
        tasks.extend(asyncio.create_task(upload(client, page, "image", "blue")) for _ in range(15))
        tasks.extend(asyncio.create_task(client.get(url_for(page, "image"))) for _ in range(15))
        await asyncio.wait_for(waiting.wait(), timeout=10)
        assert engine.pool.checkedout() == 0
        assert all(not task.done() for task in tasks)
        # Only the first upload may enter storage for this page before release.
        assert key not in storage.objects
        assert storage.entered.empty()
        await browse_and_upload(client, pages[15], "image")
    finally:
        gate.release.set()
        responses = await asyncio.wait_for(asyncio.gather(*tasks), timeout=15)
    assert all(response.status_code == 200 for response in responses)
    assert storage.objects[key] == image_bytes("blue")
    for width in (None, 64, 128):
        response = await client.get(url_for(page, "image"), params={} if width is None else {"width": width})
        assert response.status_code == 200
        with Image.open(io.BytesIO(response.content)) as image:
            red, _, blue = image.getpixel((0, 0))
            assert blue > red
    assert engine.pool.checkedout() == 0
