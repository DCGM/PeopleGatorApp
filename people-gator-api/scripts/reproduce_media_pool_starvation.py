"""Reproduce issue #10 with disposable PostgreSQL and a gated local S3 endpoint.

From people-gator-api: uv run --locked python scripts/reproduce_media_pool_starvation.py
Exit 0 means the current starvation bug was reproduced, not that it was fixed.
Pass --expect-fixed to require independent requests to complete before release.
"""

import argparse
import asyncio
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time


API_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def disposable_postgres():
    container = subprocess.check_output([
        "docker", "run", "--rm", "--detach",
        "--publish", "127.0.0.1::5432",
        "--env", "POSTGRES_USER=test", "--env", "POSTGRES_PASSWORD=test",
        "--env", "POSTGRES_DB=issue10_repro", "pgvector/pgvector:pg16",
    ], text=True).strip()
    try:
        deadline = time.monotonic() + 30
        while subprocess.run([
            "docker", "exec", container, "pg_isready", "-U", "test", "-d", "issue10_repro",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            if time.monotonic() >= deadline:
                raise TimeoutError("Disposable PostgreSQL did not become ready")
            time.sleep(0.2)
        address = subprocess.check_output([
            "docker", "port", container, "5432/tcp",
        ], text=True).strip()
        yield int(address.rsplit(":", 1)[1])
    finally:
        subprocess.run(["docker", "rm", "--force", container], check=True,
                       stdout=subprocess.DEVNULL)


async def reproduce(storage: Path, *, expect_fixed: bool = False):
    # Initialize the schema package before the existing shared settings imports.
    import people_gator_api.schemas  # noqa: F401
    from aiohttp import web
    from alembic import command
    import httpx
    from PIL import Image
    import uvicorn

    from people_gator_api.app import get_app
    from people_gator_api.filesystem.local import LocalFilesystem
    from people_gator_api.media.page_image import page_image_key
    from people_gator_api.media.page_layout import page_layout_key
    from people_gator_api.persistence.postgres.schema import migration_config
    from people_gator_api.schemas.common import GenericActor
    from people_gator_api.seeding.preview import seed_preview
    from people_gator_api.services.auth_service import get_current_user
    from people_gator_api.services import database_service
    from people_gator_api.settings import S3Settings, StorageSettings, PageImageCacheSettings, settings

    await asyncio.to_thread(command.upgrade, migration_config(), "head")
    try:
        async for database in database_service.get_database():
            filesystem = LocalFilesystem(storage)
            seeded = await seed_preview(database, filesystem)
            await seed_preview(database, filesystem)
            pages = [await database.sources.get_page(source_id)
                     for source_id in list(seeded.pages.values())[:16]]
    finally:
        await database_service.close_db()

    held_keys = set()
    entered_keys = set()
    entered = asyncio.Event()
    release = asyncio.Event()
    objects = {}

    async def s3(request):
        key = request.match_info["key"]
        payload = await request.read()
        if request.method == "PUT":
            if key in held_keys:
                entered_keys.add(key)
                if entered_keys == held_keys:
                    entered.set()
                await release.wait()
            objects[key] = payload
            return web.Response(headers={"ETag": '"synthetic"'})
        if request.method == "GET" and key in objects:
            return web.Response(body=objects[key])
        return web.Response(status=404, content_type="application/xml",
                            text="<Error><Code>NoSuchKey</Code></Error>")

    s3_app = web.Application()
    s3_app.router.add_route("*", "/issue10/{key:.*}", s3)
    runner = web.AppRunner(s3_app, access_log=None)
    await runner.setup()
    server = None
    server_task = None
    api_socket = None
    try:
        s3_site = web.TCPSite(runner, "127.0.0.1", 0)
        await s3_site.start()
        s3_port = runner.addresses[0][1]
        settings.storage = StorageSettings(s3=S3Settings(
            access_key_id="synthetic", secret_access_key="synthetic",
            bucket_name="issue10", region="us-east-1", timeout_seconds=30,
            endpoint_url=f"http://127.0.0.1:{s3_port}",
        ))
        settings.page_image_cache = PageImageCacheSettings(widths=[64, 128])
        app = get_app()
        app.dependency_overrides[get_current_user] = lambda: GenericActor(
            user_id=seeded.users["reviewer"],
        )
        api_socket = socket.socket()
        api_socket.bind(("127.0.0.1", 0))
        api_port = api_socket.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level="error", access_log=False))
        server_task = asyncio.create_task(server.serve(sockets=[api_socket]))
        async with asyncio.timeout(15):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise RuntimeError("API failed to start")
                await asyncio.sleep(0.02)

        image = io.BytesIO()
        Image.new("RGB", (160, 80), "blue").save(image, format="PNG")
        layout = {"id": "issue10", "page_size": [160, 80], "regions": [], "reading_order": {}}

        def media_url(page, resource):
            return f"/api/v1/pages/{page.source_id}/{resource}"

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{api_port}", timeout=20) as client:
            async def upload(page, resource):
                if resource == "image":
                    return await client.put(media_url(page, resource), files={
                        "file": ("scan.png", image.getvalue(), "image/png"),
                    })
                return await client.put(media_url(page, resource), json=layout)

            for resource in ("image", "page-layout"):
                for count in (14, 15):
                    key_fn = page_image_key if resource == "image" else page_layout_key
                    held_keys.clear()
                    held_keys.update(key_fn(p.library, p.document_id, p.page_id) for p in pages[:count])
                    entered_keys.clear()
                    entered.clear()
                    release.clear()
                    uploads = [asyncio.create_task(upload(p, resource)) for p in pages[:count]]
                    probes = {}
                    try:
                        await asyncio.wait_for(entered.wait(), timeout=15)
                        pool = database_service._postgres_engine.pool
                        assert pool.checkedout() == (0 if expect_fixed else count), pool.status()
                        pool_status = pool.status()
                        probes = {
                            "list": asyncio.create_task(client.get("/api/v1/entities")),
                            "search": asyncio.create_task(client.get(
                                "/api/v1/search-entities", params={"query.text": "Ada"},
                            )),
                            "independent-upload": asyncio.create_task(upload(pages[15], resource)),
                            "health": asyncio.create_task(client.get("/api/v1/health")),
                        }
                        # Gates, not a minute-long storage sleep, control this observation.
                        await asyncio.wait(probes.values(), timeout=5 if expect_fixed else 1)
                        blocked = sorted(name for name, task in probes.items() if not task.done())
                        expected = ["independent-upload", "list", "search"] if count == 15 and not expect_fixed else []
                        assert blocked == expected, (resource, count, blocked)
                        assert probes["health"].done() and probes["health"].result().status_code == 200
                        assert all(not task.done() for task in uploads)
                        print(json.dumps({"resource": resource, "held_uploads": count,
                                          "pool": pool_status, "blocked": blocked,
                                          "health": 200}), flush=True)
                    finally:
                        release.set()
                        responses = await asyncio.wait_for(
                            asyncio.gather(*uploads, *probes.values()), timeout=15,
                        )
                    assert all(response.status_code == 200 for response in responses)
                    for name in ("list", "search"):
                        assert probes[name].result().json()["items"], name
                    fetched = await client.get(media_url(pages[15], resource))
                    assert fetched.status_code == 200
                    receipt = probes["independent-upload"].result().json()
                    assert receipt["source_id"] == str(pages[15].source_id)
                    if resource == "image":
                        assert receipt["media_type"] == "image/jpeg"
                        assert receipt["size_bytes"] == len(fetched.content)
                        with Image.open(io.BytesIO(fetched.content)) as stored:
                            stored.load()
                            assert stored.size == (160, 80) and stored.format == "JPEG"
                    else:
                        assert receipt["media_type"] == "application/json"
                        assert fetched.json() == layout
    finally:
        release.set()
        if server is not None:
            server.should_exit = True
        try:
            if server_task is not None:
                await asyncio.wait_for(server_task, timeout=15)
        finally:
            if api_socket is not None:
                api_socket.close()
            await runner.cleanup()
    print(
        "FIXED: independent requests complete with 14 and 15 stalled uploads."
        if expect_fixed else
        "REPRODUCED: 15 stalled uploads starve database requests; 14 do not.",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-fixed", action="store_true")
    args = parser.parse_args()
    with disposable_postgres() as port, tempfile.TemporaryDirectory(prefix="issue10-") as temporary:
        # Ignore inherited application settings and .env files; only our container is used.
        for name in list(os.environ):
            if name.startswith("PEOPLE_GATOR_API__"):
                del os.environ[name]
        os.environ["PYTHON_DOTENV_DISABLED"] = "1"
        os.environ["PEOPLE_GATOR_API__PERSISTENCE"] = json.dumps({"postgres": {
            "host": "127.0.0.1", "port": port, "user": "test", "password": "test",
            "database": "issue10_repro", "schema_mode": "validate",
        }, "weaviate": None})
        storage = Path(temporary) / "storage"
        os.environ["PEOPLE_GATOR_API__STORAGE"] = json.dumps({
            "local": {"root": str(storage)}, "s3": None,
        })
        # migration_config resolves this symlink to the repository's real Alembic config.
        (Path(temporary) / "alembic.ini").symlink_to(API_ROOT / "alembic.ini")
        original_directory = Path.cwd()
        try:
            os.chdir(temporary)
            asyncio.run(reproduce(storage, expect_fixed=args.expect_fixed))
        finally:
            os.chdir(original_directory)


if __name__ == "__main__":
    main()
