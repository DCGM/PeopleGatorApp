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
    assert await counts(database) == (6, 12, 10)
    assert len(result.documents) == 8 and len(result.pages) == 13
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
            {"ada-candidate"},
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
            item.detection_id for item in hits.items[:5]
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
            result.mentions[item.key] for item in page.mentions if item.state is not None
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
    assert await counts(database) == (6, 12, 10)
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
    assert await counts(database) == (7, 12, 10)


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
    assert len(result.entities) == 6 and len(result.faces) == 12
    assert await counts(database) == (6, 12, 10)


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
    assert await counts(database) == (5, 11, 9)


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


@pytest.mark.asyncio
async def test_link_states_transitions_filters_stats_and_rerun(seed_target):
    from people_gator_api.schemas.enums import EntityLinkState as State
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionPatchRequest, TextMentionListFilter
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.common import GenericActor

    db, fs, engine = seed_target
    seed = await preview.seed_preview(db, fs)
    reviewer = GenericActor(user_id=seed.users["reviewer"])
    importer = GenericActor(user_id=seed.users["importer"], api_key_id=seed.api_keys["importer"])
    for kind, repo, ids in (("faces", db.faces, seed.faces), ("mentions", db.text_mentions, seed.mentions)):
        suffix = "-mention" if kind == "mentions" else ""
        for key, state in (("auto", State.automatic), ("manual", State.manual), ("verified", State.verified), ("unassigned", None)):
            record = await repo.get(ids["links-" + key + suffix])
            assert record.entity_link_state == state
            if state == State.verified:
                assert record.entity_link_verified_by_user_id == reviewer.user_id
                assert record.entity_link_verified_at.utcoffset().total_seconds() == 0
        assert (await repo.get(ids["links-unassigned" + suffix])).entity_id is None
    doc = await db.sources.get_document(seed.documents["link-states"])
    for counts in (doc.entity_link_stats.faces, doc.entity_link_stats.mentions):
        assert counts.model_dump() == dict(automatic=1, manual=1, verified=1, unassigned=1, total=4)
    empty = await db.sources.get_document(seed.documents["empty-document"])
    assert empty.entity_link_stats.faces.total == empty.entity_link_stats.mentions.total == 0
    page = await db.sources.get_page(seed.pages["links-1"])
    assert page.entity_link_stats.faces.verified == 0
    assert page.entity_link_stats.faces.total == 2
    for states, expected in (([State.automatic, State.manual], 2), (list(State), 3)):
        faces = await db.faces.list(FaceListRequest(filter_=FaceListFilter(source_id=list(seed.pages[k] for k in ("links-1", "links-2")), entity_link_state=states), return_total_count=True, limit=1))
        assert faces.total_count == expected and len(faces.items) == 1
    # State from another page or another entity cannot satisfy the same witness.
    entities = await db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(source_id=[seed.pages["links-1"]], entity_link_state=[State.verified])))
    assert entities.items == []
    pages = await db.sources.list_pages(PageListRequest(limit=100, filter_=PageListFilter(entity_id=[seed.entities["emil"]], entity_link_state=[State.verified])))
    assert pages.items == []
    docs = await db.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(entity_id=[seed.entities["ada"]], entity_link_state=[State.verified])))
    assert seed.documents["link-states"] in {item.source_id for item in docs.items}
    spans = await get_text_mention_spans(db, seed.pages["links-2"], library=doc.library, document_id=doc.document_id, page_id=next(p.page_id for p in PAGES if p.key == "links-2"), entity_link_state=[State.verified])
    assert len(spans) == 1 and spans[0].start_line_id != spans[0].end_line_id
    assert spans[0].mention_id == seed.mentions["links-verified-mention"]
    # Both annotation kinds follow exactly the same transition table.
    for repo, record_id, patch in ((db.faces, seed.faces["links-auto"], FacePatchRequest), (db.text_mentions, seed.mentions["links-auto-mention"], TextMentionPatchRequest)):
        before = await repo.get(record_id)
        verified = await repo.patch(record_id, patch(entity_link_state=State.verified), importer)
        assert verified.entity_link_verified_by_user_id == importer.user_id
        assert verified.entity_link_verified_at is not None
        touched = (await db.entities.get(before.entity_id)).last_touched_at
        repeat = await repo.patch(record_id, patch(entity_id=before.entity_id, entity_link_state=State.verified), reviewer)
        assert repeat.entity_link_verified_at == verified.entity_link_verified_at
        assert repeat.entity_link_verified_by_user_id == importer.user_id
        assert (await db.entities.get(before.entity_id)).last_touched_at == touched
        assert (await repo.patch(record_id, patch(), reviewer)).entity_link_verified_at == verified.entity_link_verified_at
        for invalid in (patch(entity_link_state=None), patch(entity_id=seed.entities["emil"], entity_link_state=State.verified), patch(entity_id=None, entity_link_state=State.manual), patch(entity_id=uuid.uuid4())):
            with pytest.raises(ValueError):
                await repo.patch(record_id, invalid, reviewer)
            assert (await repo.get(record_id)).entity_id == before.entity_id
        moved = await repo.patch(record_id, patch(entity_id=seed.entities["emil"]), reviewer)
        assert moved.entity_link_state == State.manual and moved.entity_link_verified_at is None
        if hasattr(before, "mention_id"):
            assert (moved.mention_id, moved.name, moved.context, moved.source_id) == (before.mention_id, before.name, before.context, before.source_id)
        cleared = await repo.patch(record_id, patch(entity_id=None), reviewer)
        assert cleared.entity_id is cleared.entity_link_state is cleared.entity_link_verified_at is None
        with pytest.raises(ValueError):
            await repo.patch(record_id, patch(entity_link_state=State.verified), reviewer)
        restored = await repo.patch(record_id, patch(entity_id=before.entity_id, entity_link_state=State.automatic), reviewer)
        assert restored.entity_link_state == State.automatic
    # Reruns preserve review changes and the verification actor/time.
    face_id = seed.faces["links-verified"]
    edited = await db.faces.patch(face_id, FacePatchRequest(entity_link_state=State.manual), reviewer)
    await preview.seed_preview(db, fs)
    assert (await db.faces.get(face_id)) == edited
    await validate_postgres_schema(engine)


@pytest.mark.asyncio
async def test_link_database_constraints_delete_merge_and_migration(seed_target):
    from sqlalchemy.exc import IntegrityError
    from people_gator_api.schemas.enums import EntityLinkState as State
    from people_gator_api.schemas.mentions import TextMentionPatchRequest
    db, fs, engine = seed_target
    seed = await preview.seed_preview(db, fs)
    actor = GenericActor(user_id=seed.users["reviewer"])
    await db.faces._session.commit()  # Release seed reads before DDL on a second connection.
    # Downgrade and upgrade are round-trippable and backfill existing assigned rows.
    async with engine.begin() as connection:
        def migrate(sync, down):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade(config, "d34a021b0003") if down else command.upgrade(config, "head"))
        await connection.run_sync(lambda sync: migrate(sync, True))
        await connection.run_sync(lambda sync: migrate(sync, False))
    for repo, record_id in ((db.faces, seed.faces["links-verified"]), (db.text_mentions, seed.mentions["links-verified-mention"])):
        record = await repo.get(record_id)
        assert record.entity_link_state == State.automatic
        assert record.entity_link_verified_at is None
    # CHECK constraints reject UNKNOWN-prone invalid combinations outside the API.
    for table, record_id in (("image_occurrences", seed.faces["links-auto"]), ("text_mentions", seed.mentions["links-auto-mention"])):
        for update in ("entity_link_state = NULL", "entity_link_state = 'verified'", "entity_link_verified_at = now()", f"entity_link_verified_by_user_id = '{actor.user_id}'"):
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(text(f"UPDATE pg_demo_{table} SET {update} WHERE id = :id"), {"id": record_id})
                await transaction.rollback()
    # A manual merge resets only the transferred links; target links keep verification.
    verified_target = await db.faces.patch(seed.faces["links-auto"], FacePatchRequest(entity_link_state=State.verified), actor)
    await db.text_mentions.patch(seed.mentions["links-manual-mention"], TextMentionPatchRequest(entity_link_state=State.verified), actor)
    merged = await db.entities.merge(seed.entities["ada"], seed.entities["emil"], context=actor)
    assert merged.merged_entity.entity_link_stats.faces.manual == merged.faces_reassigned == 3
    moved = await db.text_mentions.get(seed.mentions["links-manual-mention"])
    assert moved.entity_link_state == State.manual and moved.entity_link_verified_at is None
    assert (await db.faces.get(verified_target.detection_id)).entity_link_verified_at == verified_target.entity_link_verified_at
    # The FK's SET NULL action must also clear verification through the trigger.
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM pg_demo_entities WHERE id = :id"), {"id": seed.entities["ada"]})
    for repo, record_id in ((db.faces, seed.faces["links-auto"]), (db.text_mentions, seed.mentions["links-manual-mention"])):
        record = await repo.get(record_id)
        assert record.entity_id is record.entity_link_state is record.entity_link_verified_at is record.entity_link_verified_by_user_id is None
    doc = await db.sources.get_document(seed.documents["link-states"])
    assert doc.entity_link_stats.faces.unassigned == doc.entity_link_stats.faces.total == 4
    assert doc.entity_link_stats.mentions.unassigned == doc.entity_link_stats.mentions.total == 4
