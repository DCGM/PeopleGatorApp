"""Exercise the preview dataset against migrated PostgreSQL and real local media."""

import io
import os
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from alembic import command
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from people_gator_api.filesystem.local import LocalFilesystem
from people_gator_api.media.aligned_face_crop import get_aligned_face_crop
from people_gator_api.media.page_image import get_page_image
from people_gator_api.media.page_layout import get_page_layout
from people_gator_api.media.text_mention_spans import get_text_mention_spans
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.schema import (
    migration_config,
    validate_postgres_schema,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.entities import (
    EntityListFilter,
    EntityListRequest,
    EntityPatchRequest,
)
from people_gator_api.schemas.faces import FaceListRequest, FacePatchRequest
from people_gator_api.schemas.mentions import TextMentionListRequest
from people_gator_api.schemas.sources import (
    DocumentListRequest, DocumentLookupRequest, GenericSourceLookupRequest,
    PageListFilter, PageListRequest,
)
from people_gator_api.schemas.search import (
    QueryBase,
    SearchFacesRequest,
    SearchEntitiesRequest,
)
from people_gator_api.seeding import preview
from people_gator_api.seeding.fixtures import (
    DOCUMENTS,
    MODEL,
    PAGES,
    SECOND_MODEL,
    Person,
)
from people_gator_api.services import filesystem_service
from people_gator_api.settings import settings


@pytest_asyncio.fixture
async def seed_target(tmp_path, monkeypatch):
    url = os.getenv("PEOPLE_GATOR_SCHEMA_TEST_URL")
    if not url:
        pytest.skip("requires a disposable schema test database")
    admin = create_async_engine(url)
    schema = "preview_seed_" + uuid.uuid4().hex
    async with admin.begin() as connection:
        for extension in ("vector", "pg_trgm", "unaccent"):
            await connection.execute(
                text(f"CREATE EXTENSION IF NOT EXISTS {extension} WITH SCHEMA public")
            )
        await connection.execute(text(f"CREATE SCHEMA {schema}"))
        # Keep Alembic from discovering a public version table through search_path
        # when the full schema test suite has already migrated the public schema.
        await connection.execute(
            text(
                f"CREATE TABLE {schema}.alembic_version (version_num VARCHAR(32) PRIMARY KEY)"
            )
        )
    engine = create_async_engine(
        url, connect_args={"server_settings": {"search_path": schema + ",public"}}
    )
    try:

        def migrate(connection):
            config = migration_config()
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

        async with engine.begin() as connection:
            await connection.run_sync(migrate)
        filesystem = LocalFilesystem(tmp_path)
        monkeypatch.setattr(filesystem_service, "get_filesystem", lambda: filesystem)
        monkeypatch.setattr(settings.aligned_face_crop, "cache_enabled", False)
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            yield postgres_database(session), filesystem, engine
    finally:
        await engine.dispose()
        async with admin.begin() as connection:
            await connection.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        await admin.dispose()


async def counts(database):
    return (
        (
            await database.entities.list(
                EntityListRequest(limit=0, return_total_count=True)
            )
        ).total_count,
        (
            await database.faces.list(FaceListRequest(limit=0, return_total_count=True))
        ).total_count,
        (
            await database.text_mentions.list(
                TextMentionListRequest(limit=0, return_total_count=True)
            )
        ).total_count,
    )


@pytest.mark.asyncio
async def test_seed_graph_vectors_filters_and_media_are_usable(seed_target):
    database, filesystem, engine = seed_target
    result = await preview.seed_preview(database, filesystem)
    assert await counts(database) == (6, 8, 6)
    assert len(result.documents) == 7 and len(result.pages) == 11
    assert len(result.users) == 3 and len(result.api_keys) == 2
    await validate_postgres_schema(engine)
    demo = parse_qs(urlsplit(result.filter_examples["mobile-filters"]).query)
    assert demo["document"] == [str(result.documents["album"])]
    assert demo["touched_by"] == [str(result.users["importer"])]
    assert demo["api_key"] == [str(result.api_keys["importer"])]
    matching = await database.entities.search(
        SearchEntitiesRequest(
            limit=100,
            query=QueryBase(text=demo["q"]),
            filter_=EntityListFilter(
                has_detections=True,
                document_source_id=[result.documents["album"]],
                last_touched_by_user_id=[result.users["importer"]],
                last_touched_by_api_key_id=[result.api_keys["importer"]],
            ),
        )
    )
    assert {item.entity_id for item in matching.items} == {
        result.entities["ada"],
        result.entities["ada-candidate"],
    }

    ada = await database.entities.get(result.entities["ada"])
    nora = await database.entities.get(result.entities["nora"])
    emil = await database.entities.get(result.entities["emil"])
    assert ada.user_id == result.users["reviewer"]
    assert ada.last_touched_by_user_id == result.users["importer"]
    assert ada.last_touched_by_api_key_id == result.api_keys["importer"]
    assert nora.last_touched_by_api_key_id == result.api_keys["ocr"]
    assert emil.last_touched_by_user_id == result.users["reviewer"]
    assert emil.last_touched_by_api_key_id is None

    for filters, expected in (
        (
            EntityListFilter(has_detections=True, has_mentions=False),
            {"emil", "ada-candidate"},
        ),
        (EntityListFilter(has_detections=False, has_mentions=True), {"nora"}),
        (EntityListFilter(has_detections=False, has_mentions=False), {"lenka"}),
        (
            EntityListFilter(document_source_id=[result.documents["album"]]),
            {"ada", "emil", "ada-candidate"},
        ),
        (
            EntityListFilter(last_touched_by_api_key_id=[result.api_keys["ocr"]]),
            {"nora"},
        ),
    ):
        found = await database.entities.list(
            EntityListRequest(limit=100, filter_=filters)
        )
        assert {item.entity_id for item in found.items} == {
            result.entities[key] for key in expected
        }

    for model in (MODEL, SECOND_MODEL):
        hits = await database.faces.search(
            SearchFacesRequest(
                limit=8,
                query=QueryBase(
                    face_id=[result.faces["ada-portrait"]],
                    face_embedding_model=model,
                ),
            )
        )
        assert result.faces["unassigned-ada"] in {
            item.detection_id for item in hits.items[:3]
        }
        entities = await database.entities.search(
            SearchEntitiesRequest(
                limit=6,
                query=QueryBase(
                    face_id=[result.faces["ada-portrait"]],
                    face_embedding_model=model,
                ),
            )
        )
        assert result.entities["ada-candidate"] in {
            item.entity_id for item in entities.items[:2]
        }

    for page in PAGES:
        document = next(item for item in DOCUMENTS if item.key == page.document)
        content = await get_page_image(
            document.library, document.document_id, page.page_id
        )
        with Image.open(io.BytesIO(content.content)) as image:
            assert image.size == (800, 1100)
        layout = await get_page_layout(
            document.library, document.document_id, page.page_id
        )
        assert layout.page_size == (1100, 800)
        spans = await get_text_mention_spans(
            database,
            result.pages[page.key],
            library=document.library,
            document_id=document.document_id,
            page_id=page.page_id,
        )
        assert {span.mention_id for span in spans} == {
            result.mentions[item.key] for item in page.mentions
        }
        for spec in page.faces:
            face = await database.faces.get(result.faces[spec.key])
            assert face.bounding_box.x + face.bounding_box.width <= 800
            assert face.bounding_box.y + face.bounding_box.height <= 1100
            source = await database.sources.lookup(
                GenericSourceLookupRequest(source_id=result.pages[page.key])
            )
            crop = await get_aligned_face_crop(
                result.users["reviewer"], face, source, max_width=256
            )
            with Image.open(io.BytesIO(crop.content)) as image:
                assert 0 < image.width <= 256 and image.width == image.height


@pytest.mark.asyncio
async def test_reruns_preserve_review_edits_and_add_new_scenarios(
    seed_target, monkeypatch
):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    actor = GenericActor(user_id=first.users["reviewer"])
    edited = await database.entities.patch(
        first.entities["ada"], EntityPatchRequest(name="Reviewed Ada"), actor
    )
    await database.faces.patch(
        first.faces["unassigned-ada"],
        FacePatchRequest(entity_id=first.entities["lenka"]),
        actor,
    )
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    assert await counts(database) == (6, 8, 6)
    stored = await database.entities.get(first.entities["ada"])
    assert (
        stored.name == "Reviewed Ada"
        and stored.last_touched_at == edited.last_touched_at
    )
    assert (
        await database.faces.get(first.faces["unassigned-ada"])
    ).entity_id == first.entities["lenka"]
    monkeypatch.setattr(
        preview,
        "PEOPLE",
        (
            *preview.PEOPLE,
            Person(
                "new-feature", "New preview scenario", (), "New coverage", "reviewer"
            ),
        ),
    )
    updated = await preview.seed_preview(database, filesystem)
    assert updated.entities["ada"] == first.entities["ada"]
    assert "new-feature" in updated.entities
    assert await counts(database) == (7, 8, 6)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_checkpoint", [1, 7])
async def test_retry_recovers_a_write_before_its_checkpoint(
    seed_target, monkeypatch, failed_checkpoint
):
    database, filesystem, _ = seed_target
    original_write = filesystem.write_bytes
    checkpoints = 0

    async def write(key, content):
        nonlocal checkpoints
        if key == preview.MANIFEST_KEY:
            checkpoints += 1
            if checkpoints == failed_checkpoint:
                raise OSError("interrupted seed checkpoint")
        await original_write(key, content)

    monkeypatch.setattr(filesystem, "write_bytes", write)
    with pytest.raises(OSError, match="interrupted"):
        await preview.seed_preview(database, filesystem)
    result = await preview.seed_preview(database, filesystem)
    assert len(result.entities) == 6 and len(result.faces) == 8
    assert await counts(database) == (6, 8, 6)


@pytest.mark.asyncio
async def test_reruns_do_not_resurrect_merged_people_or_deleted_evidence(seed_target):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    actor = GenericActor(user_id=first.users["reviewer"])
    await database.entities.merge(
        first.entities["ada"], first.entities["ada-candidate"], context=actor
    )
    await database.faces.delete(first.faces["unassigned-other"], context=actor)
    await database.text_mentions.delete(first.mentions["nora-letter"], context=actor)
    second = await preview.seed_preview(database, filesystem)
    assert "ada-candidate" not in second.entities
    assert "unassigned-other" not in second.faces
    assert "nora-letter" not in second.mentions
    assert (
        await database.faces.get(first.faces["ada-candidate"])
    ).entity_id == first.entities["ada"]
    assert await counts(database) == (5, 7, 5)


@pytest.mark.asyncio
async def test_document_groups_names_and_scan_only_media(seed_target):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    listed = await database.sources.list_documents(DocumentListRequest(limit=100))
    assert {item.source_id for item in listed.items} == set(first.documents.values())
    for key, expected_pages in (("grouped-album", 2), ("grouped-mirror", 1), ("empty-document", 0), ("legacy-document", 1)):
        spec = next(item for item in DOCUMENTS if item.key == key)
        document = await database.sources.lookup_document(DocumentLookupRequest(
            library=spec.library, document_id=spec.document_id,
        ))
        assert document.name == (spec.title if spec.named else None)
        assert (await database.sources.get_document(document.source_id)).name == document.name
        pages = await database.sources.list_pages(PageListRequest(
            limit=1, return_total_count=True,
            filter_=PageListFilter(library=[spec.library], document_id=[spec.document_id]),
        ))
        assert pages.total_count == expected_pages
        all_pages = list(pages.items)
        if pages.cursor:
            more = await database.sources.list_pages(PageListRequest(
                limit=1, cursor=pages.cursor, return_total_count=True,
                filter_=PageListFilter(library=[spec.library], document_id=[spec.document_id]),
            ))
            all_pages.extend(more.items)
        assert len({item.source_id for item in all_pages}) == expected_pages
        assert all(item.library == spec.library and item.document_id == spec.document_id for item in all_pages)
    orphan = next(item for item in DOCUMENTS if item.key == "scan-only")
    assert await database.sources.lookup_document(DocumentLookupRequest(
        library=orphan.library, document_id=orphan.document_id,
    )) is None
    page = next(item for item in PAGES if item.document == orphan.key)
    content = await get_page_image(orphan.library, orphan.document_id, page.page_id)
    assert content.content


@pytest.mark.asyncio
async def test_document_registration_api_names_and_legacy_requests(seed_target):
    from fastapi import HTTPException
    from people_gator_api.routes.v1.media import (
        create_document_route, create_document_batch_route, get_document_route,
        lookup_document_route, list_documents_route,
    )
    from people_gator_api.schemas.common import GenericListRequest
    from people_gator_api.schemas.sources import DocumentCreateRequest, DocumentListFilter

    database, _, _ = seed_target
    request = DocumentCreateRequest(library="names-test", document_id=uuid.uuid4(), name="  Named album  ")
    created = await create_document_route(payload=request, database=database, user=None)
    assert created.name == "Named album"
    assert (await get_document_route(document_source_id=created.source_id, database=database, user=None)).name == created.name
    assert (await lookup_document_route(database=database, user=None, library=request.library, document_id=request.document_id)).name == created.name
    legacy = DocumentCreateRequest(library="names-test", document_id=uuid.uuid4())
    batch = await create_document_batch_route(payload=[request.model_copy(update={"name": "Replacement"}), legacy], database=database, user=None)
    assert [item.name for item in batch] == ["Named album", None]
    with pytest.raises(HTTPException) as conflict:
        await create_document_route(payload=request, database=database, user=None)
    assert conflict.value.status_code == 409
    listed = await list_documents_route(database=database, user=None, filter=DocumentListFilter(library=["names-test"]), list_request=GenericListRequest(limit=100))
    assert {item.source_id: item.name for item in listed.items} == {created.source_id: "Named album", batch[1].source_id: None}


@pytest.mark.asyncio
async def test_document_name_migration_preserves_existing_sources(seed_target):
    database, _, engine = seed_target
    document_source, page_source, document_id, page_id = (uuid.uuid4() for _ in range(4))
    async with engine.begin() as connection:
        def migrate_to(sync, revision, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, revision)

        await connection.run_sync(lambda sync: migrate_to(sync, "d34a021b0002", True))
        for source_id, kind, url in (
            (document_source, "document", f"https://www.digitalniknihovna.cz/legacy/view/uuid:{document_id}"),
            (page_source, "page", f"https://www.digitalniknihovna.cz/legacy/view/uuid:{document_id}?page=uuid:{page_id}"),
        ):
            await connection.execute(text("INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, :kind, :url)"), {"id": source_id, "kind": kind, "url": url})
        await connection.execute(text("INSERT INTO pg_demo_documents (id, library, document_id) VALUES (:id, 'legacy', :document)"), {"id": document_source, "document": document_id})
        await connection.execute(text("INSERT INTO pg_demo_pages (id, library, document_id, page_id) VALUES (:id, 'legacy', :document, :page)"), {"id": page_source, "document": document_id, "page": page_id})
        await connection.run_sync(lambda sync: migrate_to(sync, "head"))
    await validate_postgres_schema(engine)
    document = await database.sources.get_document(document_source)
    page = await database.sources.get_page(page_source)
    assert document.name is None and document.document_id == document_id
    assert page.document_id == document_id and page.page_id == page_id
