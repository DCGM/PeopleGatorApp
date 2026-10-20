"""Exercise the preview dataset against migrated PostgreSQL and real local media."""

import io
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from alembic import command
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.filesystem.local import LocalFilesystem
from people_gator_api.media.aligned_face_crop import get_aligned_face_crop
from people_gator_api.media.page_image import get_page_image
from people_gator_api.media.page_layout import get_page_layout
from people_gator_api.media.errors import SourceResolutionError
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
    DocumentListRequest,
    DocumentLookupRequest,
    GenericSourceLookupRequest,
    PageListFilter,
    PageListRequest,
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
async def seed_target(tmp_path, monkeypatch, migrated_postgres):
    filesystem = LocalFilesystem(tmp_path)
    monkeypatch.setattr(filesystem_service, "get_filesystem", lambda: filesystem)
    monkeypatch.setattr(settings.aligned_face_crop, "cache_enabled", False)
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        yield postgres_database(session), filesystem, migrated_postgres


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
    assert await counts(database) == (9, 25, 14)
    assert len(result.documents) == 15 and len(result.pages) == 26
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
                entity_link_state=demo["link_state"],
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
        if page.has_layout:
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
                result.mentions[item.key]
                for item in page.mentions
                if item.state is not None
            }
        else:
            with pytest.raises(SourceResolutionError) as missing_layout:
                await get_page_layout(document.library, document.document_id, page.page_id)
            assert missing_layout.value.status_code == 404
            stored = await database.sources.get_page(result.pages[page.key])
            assert stored.entity_link_stats.faces.unassigned == 2
            assert stored.entity_link_stats.mentions.total == 0
            link = urlsplit(result.filter_examples["faces-without-ocr"])
            assert link.path.endswith(f"/pages/{stored.page_id}")
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
    assert await counts(database) == (9, 25, 14)
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
    assert await counts(database) == (10, 25, 14)


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
    assert len(result.entities) == 9 and len(result.faces) == 25
    assert await counts(database) == (9, 25, 14)


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
    assert await counts(database) == (8, 24, 13)


@pytest.mark.asyncio
async def test_no_ocr_scan_preserves_face_review_and_media_on_rerun(seed_target):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    actor = GenericActor(user_id=first.users["reviewer"])
    face = await database.faces.patch(
        first.faces["no-ocr-left"],
        FacePatchRequest(entity_id=first.entities["lenka"], entity_link_state="manual"),
        actor,
    )
    source = await database.sources.get_page(first.pages["faces-no-ocr-1"])
    before = await get_page_image(source.library, source.document_id, source.page_id)
    second = await preview.seed_preview(database, filesystem)
    assert second.pages["faces-no-ocr-1"] == source.source_id
    assert second.faces["no-ocr-left"] == face.detection_id
    retained = await database.faces.get(face.detection_id)
    assert retained.entity_id == first.entities["lenka"]
    assert retained.entity_link_state == "manual"
    reviewed = await database.entities.get(first.entities["lenka"])
    timestamp = reviewed.last_touched_at
    await preview.seed_preview(database, filesystem)
    assert (await database.entities.get(first.entities["lenka"])).last_touched_at == timestamp
    after = await get_page_image(source.library, source.document_id, source.page_id)
    assert after.content == before.content
    with pytest.raises(SourceResolutionError) as missing_layout:
        await get_page_layout(source.library, source.document_id, source.page_id)
    assert missing_layout.value.status_code == 404
    statistics = (await database.sources.get_page(source.source_id)).entity_link_stats
    assert statistics.faces.manual == 1 and statistics.faces.unassigned == 1


@pytest.mark.asyncio
async def test_document_groups_names_and_scan_only_media(seed_target):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    listed = await database.sources.list_documents(DocumentListRequest(limit=100))
    assert {item.source_id for item in listed.items} == set(first.documents.values())
    for key, expected_pages in (
        ("grouped-album", 2),
        ("grouped-mirror", 1),
        ("empty-document", 0),
        ("legacy-document", 1),
    ):
        spec = next(item for item in DOCUMENTS if item.key == key)
        document = await database.sources.lookup_document(
            DocumentLookupRequest(
                library=spec.library,
                document_id=spec.document_id,
            )
        )
        assert document.name == (spec.title if spec.named else None)
        assert (
            await database.sources.get_document(document.source_id)
        ).name == document.name
        pages = await database.sources.list_pages(
            PageListRequest(
                limit=1,
                return_total_count=True,
                filter_=PageListFilter(
                    library=[spec.library], document_id=[spec.document_id]
                ),
            )
        )
        assert pages.total_count == expected_pages
        all_pages = list(pages.items)
        if pages.cursor:
            more = await database.sources.list_pages(
                PageListRequest(
                    limit=1,
                    cursor=pages.cursor,
                    return_total_count=True,
                    filter_=PageListFilter(
                        library=[spec.library], document_id=[spec.document_id]
                    ),
                )
            )
            all_pages.extend(more.items)
        assert len({item.source_id for item in all_pages}) == expected_pages
        assert all(
            item.library == spec.library and item.document_id == spec.document_id
            for item in all_pages
        )
    orphan = next(item for item in DOCUMENTS if item.key == "scan-only")
    assert (
        await database.sources.lookup_document(
            DocumentLookupRequest(
                library=orphan.library,
                document_id=orphan.document_id,
            )
        )
        is None
    )
    page = next(item for item in PAGES if item.document == orphan.key)
    content = await get_page_image(orphan.library, orphan.document_id, page.page_id)
    assert content.content


@pytest.mark.asyncio
async def test_document_registration_api_names_and_legacy_requests(seed_target):
    from fastapi import HTTPException
    from people_gator_api.routes.v1.media import (
        create_document_route,
        create_document_batch_route,
        get_document_route,
        lookup_document_route,
        list_documents_route,
    )
    from people_gator_api.schemas.common import GenericListRequest
    from people_gator_api.schemas.sources import (
        DocumentCreateRequest,
        DocumentListFilter,
    )

    database, _, _ = seed_target
    request = DocumentCreateRequest(
        library="names-test", document_id=uuid.uuid4(), name="  Named album  "
    )
    created = await create_document_route(payload=request, database=database, user=None)
    assert created.name == "Named album"
    assert (
        await get_document_route(
            document_source_id=created.source_id, database=database, user=None
        )
    ).name == created.name
    assert (
        await lookup_document_route(
            database=database,
            user=None,
            library=request.library,
            document_id=request.document_id,
        )
    ).name == created.name
    legacy = DocumentCreateRequest(library="names-test", document_id=uuid.uuid4())
    batch = await create_document_batch_route(
        payload=[request.model_copy(update={"name": "Replacement"}), legacy],
        database=database,
        user=None,
    )
    assert [item.name for item in batch] == ["Named album", None]
    with pytest.raises(HTTPException) as conflict:
        await create_document_route(payload=request, database=database, user=None)
    assert conflict.value.status_code == 409
    listed = await list_documents_route(
        database=database,
        user=None,
        filter=DocumentListFilter(library=["names-test"]),
        list_request=GenericListRequest(limit=100),
    )
    assert {item.source_id: item.name for item in listed.items} == {
        created.source_id: "Named album",
        batch[1].source_id: None,
    }


@pytest.mark.asyncio
async def test_document_name_migration_preserves_existing_sources(seed_target):
    database, _, engine = seed_target
    document_source, page_source, document_id, page_id = (
        uuid.uuid4() for _ in range(4)
    )
    async with engine.begin() as connection:

        def migrate_to(sync, revision, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, revision)

        await connection.run_sync(lambda sync: migrate_to(sync, "d34a021b0002", True))
        for source_id, kind, url in (
            (
                document_source,
                "document",
                f"https://www.digitalniknihovna.cz/legacy/view/uuid:{document_id}",
            ),
            (
                page_source,
                "page",
                f"https://www.digitalniknihovna.cz/legacy/view/uuid:{document_id}?page=uuid:{page_id}",
            ),
        ):
            await connection.execute(
                text(
                    "INSERT INTO pg_demo_sources (id, source_type, url) VALUES (:id, :kind, :url)"
                ),
                {"id": source_id, "kind": kind, "url": url},
            )
        await connection.execute(
            text(
                "INSERT INTO pg_demo_documents (id, library, document_id) VALUES (:id, 'legacy', :document)"
            ),
            {"id": document_source, "document": document_id},
        )
        await connection.execute(
            text(
                "INSERT INTO pg_demo_pages (id, library, document_id, page_id) VALUES (:id, 'legacy', :document, :page)"
            ),
            {"id": page_source, "document": document_id, "page": page_id},
        )
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
    from people_gator_api.schemas.mentions import (
        TextMentionPatchRequest,
        TextMentionListFilter,
    )
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.common import GenericActor

    db, fs, engine = seed_target
    seed = await preview.seed_preview(db, fs)
    reviewer = GenericActor(user_id=seed.users["reviewer"])
    importer = GenericActor(
        user_id=seed.users["importer"], api_key_id=seed.api_keys["importer"]
    )
    for kind, repo, ids in (
        ("faces", db.faces, seed.faces),
        ("mentions", db.text_mentions, seed.mentions),
    ):
        suffix = "-mention" if kind == "mentions" else ""
        for key, state in (
            ("auto", State.automatic),
            ("manual", State.manual),
            ("verified", State.verified),
            ("unassigned", None),
        ):
            record = await repo.get(ids["links-" + key + suffix])
            assert record.entity_link_state == state
            if state == State.verified:
                assert record.entity_link_verified_by_user_id == reviewer.user_id
                assert record.entity_link_verified_at.utcoffset().total_seconds() == 0
        assert (await repo.get(ids["links-unassigned" + suffix])).entity_id is None
    doc = await db.sources.get_document(seed.documents["link-states"])
    statistics_link = urlsplit(seed.filter_examples["link-statistics"])
    statistics_page = await db.sources.get_page(seed.pages["links-2"])
    assert statistics_link.fragment == "link-statistics"
    assert statistics_link.path == (
        f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
        f"/pages/{statistics_page.page_id}"
    )
    assert statistics_page.entity_link_stats.faces.verified == 1
    assert statistics_page.entity_link_stats.mentions.unassigned == 1
    assert statistics_page.document_id == doc.document_id
    for counts in (doc.entity_link_stats.faces, doc.entity_link_stats.mentions):
        assert counts.model_dump() == dict(
            automatic=1, manual=1, verified=1, unassigned=1, total=4
        )
    empty = await db.sources.get_document(seed.documents["empty-document"])
    assert (
        empty.entity_link_stats.faces.total
        == empty.entity_link_stats.mentions.total
        == 0
    )
    page = await db.sources.get_page(seed.pages["links-1"])
    assert page.entity_link_stats.faces.verified == 0
    assert page.entity_link_stats.faces.total == 2
    for states, expected in (([State.automatic, State.manual], 2), (list(State), 3)):
        faces = await db.faces.list(
            FaceListRequest(
                filter_=FaceListFilter(
                    source_id=list(seed.pages[k] for k in ("links-1", "links-2")),
                    entity_link_state=states,
                ),
                return_total_count=True,
                limit=1,
            )
        )
        assert faces.total_count == expected and len(faces.items) == 1
    # State from another page or another entity cannot satisfy the same witness.
    entities = await db.entities.list(
        EntityListRequest(
            limit=100,
            filter_=EntityListFilter(
                source_id=[seed.pages["links-1"]], entity_link_state=[State.verified]
            ),
        )
    )
    assert entities.items == []
    pages = await db.sources.list_pages(
        PageListRequest(
            limit=100,
            filter_=PageListFilter(
                entity_id=[seed.entities["link-emil"]],
                entity_link_state=[State.verified],
            ),
        )
    )
    assert pages.items == []
    docs = await db.sources.list_documents(
        DocumentListRequest(
            limit=100,
            filter_=DocumentListFilter(
                entity_id=[seed.entities["link-ada"]],
                entity_link_state=[State.verified],
            ),
        )
    )
    assert seed.documents["link-states"] in {item.source_id for item in docs.items}
    spans = await get_text_mention_spans(
        db,
        seed.pages["links-2"],
        library=doc.library,
        document_id=doc.document_id,
        page_id=next(p.page_id for p in PAGES if p.key == "links-2"),
        entity_link_state=[State.verified],
    )
    assert len(spans) == 1 and spans[0].start_line_id != spans[0].end_line_id
    assert spans[0].mention_id == seed.mentions["links-verified-mention"]
    # Both annotation kinds follow exactly the same transition table.
    for repo, record_id, patch in (
        (db.faces, seed.faces["links-auto"], FacePatchRequest),
        (
            db.text_mentions,
            seed.mentions["links-auto-mention"],
            TextMentionPatchRequest,
        ),
    ):
        before = await repo.get(record_id)
        verified = await repo.patch(
            record_id, patch(entity_link_state=State.verified), importer
        )
        assert verified.entity_link_verified_by_user_id == importer.user_id
        assert verified.entity_link_verified_at is not None
        touched = (await db.entities.get(before.entity_id)).last_touched_at
        repeat = await repo.patch(
            record_id,
            patch(entity_id=before.entity_id, entity_link_state=State.verified),
            reviewer,
        )
        assert repeat.entity_link_verified_at == verified.entity_link_verified_at
        assert repeat.entity_link_verified_by_user_id == importer.user_id
        assert (await db.entities.get(before.entity_id)).last_touched_at == touched
        assert (
            await repo.patch(record_id, patch(), reviewer)
        ).entity_link_verified_at == verified.entity_link_verified_at
        if repo is db.faces:
            embedded = await repo.patch(
                record_id,
                patch(
                    embeddings=[
                        preview.FaceEmbedding(
                            model_identifier=MODEL, vector=[1.0] + [0.0] * 7
                        )
                    ]
                ),
                reviewer,
            )
            assert embedded.entity_link_verified_at == verified.entity_link_verified_at
            assert embedded.entity_link_verified_by_user_id == importer.user_id
        for invalid in (
            patch(entity_link_state=None),
            patch(
                entity_id=seed.entities["link-emil"], entity_link_state=State.verified
            ),
            patch(entity_id=None, entity_link_state=State.manual),
            patch(entity_id=uuid.uuid4()),
        ):
            with pytest.raises(ValueError):
                await repo.patch(record_id, invalid, reviewer)
            assert (await repo.get(record_id)).entity_id == before.entity_id
        moved = await repo.patch(
            record_id, patch(entity_id=seed.entities["link-emil"]), reviewer
        )
        assert (
            moved.entity_link_state == State.manual
            and moved.entity_link_verified_at is None
        )
        if hasattr(before, "mention_id"):
            assert (moved.mention_id, moved.name, moved.context, moved.source_id) == (
                before.mention_id,
                before.name,
                before.context,
                before.source_id,
            )
        cleared = await repo.patch(record_id, patch(entity_id=None), reviewer)
        assert (
            cleared.entity_id
            is cleared.entity_link_state
            is cleared.entity_link_verified_at
            is None
        )
        with pytest.raises(ValueError):
            await repo.patch(
                record_id, patch(entity_link_state=State.verified), reviewer
            )
        restored = await repo.patch(
            record_id,
            patch(entity_id=before.entity_id, entity_link_state=State.automatic),
            reviewer,
        )
        assert restored.entity_link_state == State.automatic
    # Reruns preserve review changes and the verification actor/time.
    face_id = seed.faces["links-verified"]
    edited = await db.faces.patch(
        face_id, FacePatchRequest(entity_link_state=State.manual), reviewer
    )
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
    await (
        db.faces._session.commit()
    )  # Release seed reads before DDL on a second connection.
    # Downgrade and upgrade are round-trippable and backfill existing assigned rows.
    async with engine.begin() as connection:

        def migrate(sync, down):
            config = migration_config()
            config.attributes["connection"] = sync
            (
                command.downgrade(config, "d34a021b0003")
                if down
                else command.upgrade(config, "head")
            )

        await connection.run_sync(lambda sync: migrate(sync, True))
        await connection.run_sync(lambda sync: migrate(sync, False))
    for repo, record_id in (
        (db.faces, seed.faces["links-verified"]),
        (db.text_mentions, seed.mentions["links-verified-mention"]),
    ):
        record = await repo.get(record_id)
        assert record.entity_link_state == State.automatic
        assert record.entity_link_verified_at is None
    # CHECK constraints reject UNKNOWN-prone invalid combinations outside the API.
    for table, record_id in (
        ("image_occurrences", seed.faces["links-auto"]),
        ("text_mentions", seed.mentions["links-auto-mention"]),
    ):
        for update in (
            "entity_link_state = NULL",
            "entity_link_state = 'verified'",
            "entity_link_verified_at = now()",
            f"entity_link_verified_by_user_id = '{actor.user_id}'",
        ):
            async with engine.connect() as connection:
                transaction = await connection.begin()
                with pytest.raises(IntegrityError):
                    await connection.execute(
                        text(f"UPDATE pg_demo_{table} SET {update} WHERE id = :id"),
                        {"id": record_id},
                    )
                await transaction.rollback()
    # A manual merge resets only the transferred links; target links keep verification.
    verified_target = await db.faces.patch(
        seed.faces["links-auto"],
        FacePatchRequest(entity_link_state=State.verified),
        actor,
    )
    await db.text_mentions.patch(
        seed.mentions["links-manual-mention"],
        TextMentionPatchRequest(entity_link_state=State.verified),
        actor,
    )
    merged = await db.entities.merge(
        seed.entities["link-ada"], seed.entities["link-emil"], context=actor
    )
    assert (
        merged.merged_entity.entity_link_stats.faces.manual
        == merged.faces_reassigned
        == 1
    )
    moved = await db.text_mentions.get(seed.mentions["links-manual-mention"])
    assert (
        moved.entity_link_state == State.manual
        and moved.entity_link_verified_at is None
    )
    assert (
        await db.faces.get(verified_target.detection_id)
    ).entity_link_verified_at == verified_target.entity_link_verified_at
    # The FK's SET NULL action must also clear verification through the trigger.
    async with engine.begin() as connection:
        await connection.execute(
            text("DELETE FROM pg_demo_entities WHERE id = :id"),
            {"id": seed.entities["link-ada"]},
        )
    for repo, record_id in (
        (db.faces, seed.faces["links-auto"]),
        (db.text_mentions, seed.mentions["links-manual-mention"]),
    ):
        record = await repo.get(record_id)
        assert (
            record.entity_id
            is record.entity_link_state
            is record.entity_link_verified_at
            is record.entity_link_verified_by_user_id
            is None
        )
    doc = await db.sources.get_document(seed.documents["link-states"])
    assert (
        doc.entity_link_stats.faces.unassigned == doc.entity_link_stats.faces.total == 4
    )
    assert (
        doc.entity_link_stats.mentions.unassigned
        == doc.entity_link_stats.mentions.total
        == 4
    )


@pytest.mark.asyncio
async def test_entity_link_http_contract_and_batch_validation(seed_target):
    import httpx
    from fastapi import FastAPI
    from people_gator_api.routes.v1 import router
    from people_gator_api.services import database_service, auth_service
    from people_gator_api.services.auth_service import AuthContext

    db, fs, _ = seed_target
    seed = await preview.seed_preview(db, fs)
    actor = AuthContext(
        user_id=seed.users["ocr"],
        user=await db.users.get(seed.users["ocr"]),
        scopes={"people-gator:annotate", "people-gator:browse"},
        authentication_method="api_key",
        api_key_id=seed.api_keys["ocr"],
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[database_service.get_database] = lambda: db
    app.dependency_overrides[auth_service.get_auth_context] = lambda: actor
    schema = app.openapi()
    assert schema["components"]["schemas"]["EntityLinkState"]["enum"] == [
        "automatic",
        "manual",
        "verified",
    ]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        for path in ("faces", "text-mentions", "entities", "pages", "documents"):
            assert (
                await client.get(f"/api/v1/{path}?filter.entity_link_state=invalid")
            ).status_code == 422
            assert (
                await client.get(f"/api/v1/{path}?filter.entity_link_state=")
            ).status_code == 422
        for path, key, id_field in (
            ("faces", "links-auto", "detection_id"),
            ("text-mentions", "links-auto-mention", "mention_id"),
        ):
            ids = seed.faces if path == "faces" else seed.mentions
            record_id = str(ids[key])
            url = f"/api/v1/{path}/{record_id}"
            response = await client.patch(url, json={"entity_link_state": "verified"})
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["entity_link_verified_by_user_id"] == str(actor.user_id)
            assert body["entity_link_verified_at"] is not None
            for invalid in (
                {"entity_link_state": "other"},
                {"entity_link_state": None},
                {"entity_link_verified_by_user_id": str(actor.user_id)},
                {"entity_id": str(uuid.uuid4())},
                {
                    "entity_id": str(seed.entities["link-emil"]),
                    "entity_link_state": "verified",
                },
            ):
                assert (await client.patch(url, json=invalid)).status_code == 422
                assert (await client.get(url)).json()["entity_id"] == str(
                    seed.entities["link-ada"]
                )
            assert (
                await client.patch(f"/api/v1/{path}/{uuid.uuid4()}", json={})
            ).status_code == 404
            # Complete semantic preflight prevents a valid first item from changing.
            invalid_batch = [
                {id_field: record_id, "entity_id": str(seed.entities["link-emil"])},
                {
                    id_field: str(
                        ids[
                            "links-unassigned"
                            if path == "faces"
                            else "links-unassigned-mention"
                        ]
                    ),
                    "entity_link_state": "verified",
                },
            ]
            assert (
                await client.patch(f"/api/v1/{path}:batch", json=invalid_batch)
            ).status_code == 422
            assert (await client.get(url)).json()["entity_link_state"] == "verified"
            batch = await client.patch(
                f"/api/v1/{path}:batch",
                json=[
                    {id_field: record_id, "entity_id": None},
                    {id_field: str(uuid.uuid4()), "entity_link_state": "manual"},
                ],
            )
            assert batch.status_code == 200 and batch.json()[1] is None
            assert batch.json()[0]["entity_link_state"] is None


@pytest.mark.asyncio
async def test_document_scope_and_indexed_aggregates_with_larger_fixture(seed_target):
    from people_gator_api.schemas.sources import DocumentCreateRequest
    from people_gator_api.schemas.mentions import (
        TextMentionCreateRequest,
        TextMentionPatchRequest,
    )
    from people_gator_api.schemas.faces import FaceCreateRequest
    from people_gator_api.persistence.postgres.entity_link_queries import (
        load_link_stats,
    )

    db, fs, engine = seed_target
    seed = await preview.seed_preview(db, fs)
    actor = GenericActor(user_id=seed.users["reviewer"])
    doc = await db.sources.get_document(seed.documents["link-states"])
    mirror, _ = await db.sources.get_or_create_document(
        DocumentCreateRequest(library="other-link-library", document_id=doc.document_id)
    )
    direct = await db.text_mentions.create(
        TextMentionCreateRequest(
            name="Emil",
            source_id=mirror.source_id,
            entity_id=seed.entities["link-emil"],
        ),
        actor,
    )
    await db.text_mentions.patch(
        direct.mention_id, TextMentionPatchRequest(entity_link_state="verified"), actor
    )
    original = await db.sources.get_document(doc.source_id)
    assert original.entity_link_stats.mentions.total == 4
    assert (
        await db.sources.get_document(mirror.source_id)
    ).entity_link_stats.mentions.verified == 1
    unrelated = await db.entities.list(
        EntityListRequest(
            limit=100,
            filter_=EntityListFilter(
                entity_id=[seed.entities["link-emil"]],
                document_source_id=[doc.source_id],
                entity_link_state=["verified"],
            ),
        )
    )
    assert unrelated.items == []
    page_is_not_document = await db.entities.list(
        EntityListRequest(
            limit=100,
            filter_=EntityListFilter(
                document_source_id=[seed.pages["links-2"]],
                entity_link_state=["verified"],
            ),
        )
    )
    assert page_is_not_document.items == []
    direct_match = await db.entities.list(
        EntityListRequest(
            limit=100,
            filter_=EntityListFilter(
                document_source_id=[mirror.source_id], entity_link_state=["verified"]
            ),
        )
    )
    assert [item.entity_id for item in direct_match.items] == [
        seed.entities["link-emil"]
    ]
    base = await db.faces.get(seed.faces["links-auto"])
    face = FaceCreateRequest(
        source_id=seed.pages["letters-2"],
        entity_id=seed.entities["link-ada"],
        bounding_box=base.bounding_box,
        keypoints=base.keypoints,
        confidence=0.9,
    )
    # Large unrelated annotation sets make a selective page/state lookup useful.
    await db.faces.create_batch([face] * 2500, actor)
    await db.text_mentions.create_batch(
        [
            TextMentionCreateRequest(
                name="Ada",
                source_id=seed.pages["letters-2"],
                entity_id=seed.entities["link-ada"],
            )
        ]
        * 2500,
        actor,
    )
    await db.faces._session.commit()
    async with engine.begin() as connection:
        for table in ("image_occurrences", "text_mentions"):
            await connection.execute(text(f"ANALYZE pg_demo_{table}"))
            plan = await connection.scalar(
                text(
                    f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT source_id, entity_link_state, count(*) FROM pg_demo_{table} WHERE source_id = :id AND entity_link_state = 'verified' GROUP BY source_id, entity_link_state"
                ),
                {"id": seed.pages["links-2"]},
            )
            import json

            assert f"ix_pg_demo_{table}_source_state" in json.dumps(plan)
    assert (
        await db.sources.get_document(doc.source_id)
    ).entity_link_stats == original.entity_link_stats


@pytest.mark.asyncio
async def test_issue8_generic_source_processing_and_rerun(seed_target):
    from people_gator_api.schemas.sources import ImageLookupRequest
    from people_gator_api.seeding.fixtures import ISSUE8_IMAGE_URL
    from people_gator_api.media.image_content import get_image_content

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    document = await database.sources.get_document(seeded.documents['issue8-search'])
    page = await database.sources.get_page(seeded.pages['issue8-search-6'])
    sibling = await database.sources.get_page(seeded.pages['issue8-untouched'])
    mirror = await database.sources.get_document(seeded.documents['issue8-mirror'])
    orphan = await database.sources.get_page(seeded.pages['issue8-orphan-1'])
    image = await database.sources.lookup_image(ImageLookupRequest(url=ISSUE8_IMAGE_URL))
    assert document.last_touched_at == page.last_touched_at
    assert document.last_touched_by_user_id == seeded.users['reviewer']
    assert document.last_touched_by_api_key_id is None
    assert sibling.last_touched_at is None
    assert mirror.last_touched_at is None
    assert orphan.last_touched_by_api_key_id == seeded.api_keys['importer']
    assert image.last_touched_by_api_key_id == seeded.api_keys['importer']
    content, media_type = await get_image_content(ISSUE8_IMAGE_URL)
    assert media_type == 'image/png' and Image.open(io.BytesIO(content)).size == (800, 1100)
    assert Image.open(io.BytesIO(content)).format == 'PNG'
    assert content.startswith(b'\x89PNG\r\n\x1a\n')
    await preview.seed_preview(database, filesystem)
    assert (await database.sources.get_document(document.source_id)).last_touched_at == document.last_touched_at
    assert (await database.sources.get_page(orphan.source_id)).last_touched_at == orphan.last_touched_at
    assert (await database.sources.get_image(image.source_id)).last_touched_at == image.last_touched_at


@pytest.mark.asyncio
async def test_issue8_document_search_processing_filters_and_options(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter, SourceListRequest, SourceListFilter, ImageListRequest, ImageListFilter, DocumentLibraryOptionsRequest
    from people_gator_api.schemas.search import SearchDocumentsRequest, SearchPagesRequest
    from people_gator_api.schemas.enums import EntityLinkState
    from datetime import timedelta
    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    target = seeded.documents['issue8-search']
    document = await database.sources.get_document(target)
    for scenario in ('compact-document-filters', 'outline-filter-badges', 'rounded-filter-removal'):
        demo = parse_qs(urlsplit(seeded.filter_examples[scenario]).query)
        demo_results = await database.sources.search_documents(SearchDocumentsRequest(
            query=QueryBase(text=demo['q']), limit=100,
            filter_=DocumentListFilter(library=demo['library'], entity_link_state=demo['link_state'],
                has_unassigned_faces=demo['unassigned'][0] == 'yes',
                **({'last_touched_by_user_id': demo['touched_by']} if 'touched_by' in demo else {})), return_total_count=True))
        assert demo_results.total_count == 1 and demo_results.items[0].source_id == target
    for term in ('pribehy', 'PŘÍBĚHY', str(document.document_id), str(document.url), 'A. Novak'):
        result = await database.sources.search_documents(SearchDocumentsRequest(query=QueryBase(text=[term]), limit=100, return_total_count=True))
        assert target in {item.source_id for item in result.items}
        if term in ('pribehy', 'PŘÍBĚHY', 'A. Novak'):
            assert seeded.documents['issue8-mirror'] not in {item.source_id for item in result.items}
        assert result.total_count == len(result.items)
        assert len(result.items) == len({item.source_id for item in result.items})
    empty = seeded.documents['empty-document']
    found = await database.sources.search_documents(SearchDocumentsRequest(query=QueryBase(text=['awaiting scans']), limit=100))
    assert empty in {item.source_id for item in found.items}
    filters = DocumentListFilter(last_touched_from=document.last_touched_at, last_touched_to=document.last_touched_at,
        last_touched_by_user_id=[seeded.users['reviewer']], library=['preview-mzk', 'preview-nlk'],
        entity_link_state=[EntityLinkState.verified], has_unassigned_faces=False)
    result = await database.sources.list_documents(DocumentListRequest(filter_=filters, limit=1, return_total_count=True))
    assert result.total_count == 1 and result.items[0].source_id == target
    assert result.items[0].last_touched_at == document.last_touched_at
    found = await database.sources.search_documents(SearchDocumentsRequest(limit=100, query=QueryBase(text=['pribehy']), filter_=filters, return_total_count=True))
    assert found.total_count == 1 and found.items[0].last_touched_at == document.last_touched_at
    for field, value in [('last_touched_from', document.last_touched_at + timedelta(microseconds=1)), ('last_touched_to', document.last_touched_at - timedelta(microseconds=1)), ('last_touched_by_api_key_id', [seeded.api_keys['importer']])]:
        result = await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(source_id=[target], **{field:value}), return_total_count=True))
        assert result.total_count == 0
    combined = await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(entity_link_state=[EntityLinkState.verified], has_unassigned_faces=True)))
    assert seeded.documents['link-states'] in {item.source_id for item in combined.items}
    negative = await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(has_unassigned_faces=False)))
    assert empty in {item.source_id for item in negative.items}
    remainder_demo = parse_qs(urlsplit(seeded.filter_examples['document-preview-remainder']).query)
    remainder_documents = await database.sources.search_documents(SearchDocumentsRequest(
        query=QueryBase(text=remainder_demo['q']), filter_=DocumentListFilter(library=remainder_demo['library']), limit=100))
    assert [item.source_id for item in remainder_documents.items] == [target]
    previews = await database.sources.list_pages(PageListRequest(filter_=PageListFilter(library=[document.library], document_id=[document.document_id]), limit=4, return_total_count=True))
    assert previews.total_count == 6 and len(previews.items) == 4
    remainder = await database.sources.list_pages(PageListRequest(filter_=PageListFilter(library=[document.library], document_id=[document.document_id]), limit=4, cursor=previews.cursor, return_total_count=True))
    assert any(item.entity_link_stats.faces.total for item in remainder.items)
    # Source and page filters use their own stored history, including orphan pages.
    own = await database.sources.list_pages(PageListRequest(limit=100, filter_=PageListFilter(last_touched_by_api_key_id=[seeded.api_keys['importer']])))
    assert seeded.pages['issue8-orphan-1'] in {item.source_id for item in own.items}
    assert seeded.pages['issue8-untouched'] not in {item.source_id for item in own.items}
    pages = await database.sources.search_pages(SearchPagesRequest(limit=100, query=QueryBase(text=['A. Novak']), filter_=PageListFilter(last_touched_by_user_id=[seeded.users['reviewer']])))
    assert seeded.pages['issue8-search-6'] in {item.source_id for item in pages.items}
    images = await database.sources.list_images(ImageListRequest(limit=100, filter_=ImageListFilter(last_touched_by_api_key_id=[seeded.api_keys['importer']])))
    assert len(images.items) == 1 and images.items[0].last_touched_at
    sources = await database.sources.list_sources(SourceListRequest(filter_=SourceListFilter(last_touched_by_api_key_id=[seeded.api_keys['importer']]), limit=100))
    assert {item.source_id for item in images.items} <= {item.source_id for item in sources.items}
    first = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, return_total_count=True))
    second = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=first.cursor, return_total_count=True))
    assert first.total_count == 2
    assert [first.items[0].library, second.items[0].library] == ['preview-mzk', 'preview-nlk']
    with pytest.raises(ValueError, match='cursor'):
        await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=first.cursor, q='mzk'))


@pytest.mark.asyncio
async def test_issue8_annotation_noops_delete_merge_rollback_and_concurrency(seed_target, monkeypatch):
    import asyncio
    from people_gator_api.schemas.sources import ImageLookupRequest
    from people_gator_api.schemas.mentions import TextMentionPatchRequest
    from people_gator_api.schemas.faces import FacePatchBatchItem
    from people_gator_api.seeding.fixtures import ISSUE8_IMAGE_URL
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from people_gator_api.persistence.postgres import face_repository

    database, filesystem, engine = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    actor = GenericActor(user_id=seeded.users['reviewer'])
    image = await database.sources.lookup_image(ImageLookupRequest(url=ISSUE8_IMAGE_URL))
    face_id = seeded.faces['issue8-image-face']
    await database.faces.patch(face_id, FacePatchRequest(), actor)
    assert (await database.sources.get_image(image.source_id)).last_touched_at == image.last_touched_at
    await database.faces.patch(face_id, FacePatchRequest(entity_id=seeded.entities['lenka']), actor)
    changed = await database.sources.get_image(image.source_id)
    assert changed.last_touched_at > image.last_touched_at and changed.last_touched_by_api_key_id is None
    # Failed commit rolls back the annotation and both kinds of metadata.
    original_commit = face_repository.commit
    async def fail(session, message):
        await session.rollback()
        raise RuntimeError('forced rollback')
    monkeypatch.setattr(face_repository, 'commit', fail)
    with pytest.raises(RuntimeError, match='rollback'):
        await database.faces.patch(face_id, FacePatchRequest(entity_id=seeded.entities['ada']), actor)
    monkeypatch.setattr(face_repository, 'commit', original_commit)
    assert (await database.faces.get(face_id)).entity_id == seeded.entities['lenka']
    assert (await database.sources.get_image(image.source_id)).last_touched_at == changed.last_touched_at
    # A batch assigns the exact same timestamp to all source targets and parents.
    await database.faces.patch_batch([
        FacePatchBatchItem(detection_id=face_id, entity_id=None),
        FacePatchBatchItem(detection_id=seeded.faces['issue8-orphan-face'], entity_id=seeded.entities['lenka']),
        FacePatchBatchItem(detection_id=seeded.faces['issue8-face-2'], entity_id=seeded.entities['lenka']),
    ], actor)
    image = await database.sources.get_image(image.source_id)
    orphan = await database.sources.get_page(seeded.pages['issue8-orphan-1'])
    page = await database.sources.get_page(seeded.pages['issue8-search-2'])
    document = await database.sources.get_document(seeded.documents['issue8-search'])
    assert image.last_touched_at == orphan.last_touched_at == page.last_touched_at == document.last_touched_at
    assert (await database.sources.get_page(seeded.pages['issue8-untouched'])).last_touched_at is None
    await database.text_mentions.patch(seeded.mentions['issue8-mention-5'], TextMentionPatchRequest(entity_id=None), actor)
    mention_page = await database.sources.get_page(seeded.pages['issue8-search-5'])
    assert mention_page.last_touched_at == (await database.sources.get_document(document.source_id)).last_touched_at
    assert await database.text_mentions.delete(seeded.mentions['issue8-mention-5'], context=actor)
    assert (await database.sources.get_page(mention_page.source_id)).last_touched_at > mention_page.last_touched_at
    await database.entities.merge(seeded.entities['ada'], seeded.entities['lenka'], context=actor)
    assert (await database.sources.get_page(orphan.source_id)).last_touched_at > orphan.last_touched_at
    await database.entities.delete(seeded.entities['ada'], context=actor)
    assert (await database.faces.get(seeded.faces['issue8-face-2'])).entity_id is None
    before = await database.sources.get_document(document.source_id)
    assert await database.sources.delete(page.source_id, context=actor)
    assert (await database.sources.get_document(document.source_id)).last_touched_at > before.last_touched_at
    assert await database.sources.get_page(page.source_id) is None
    # Concurrent independent edits of siblings serialize parent processing.
    async def edit(face_id, entity_id):
        async with async_sessionmaker(engine, expire_on_commit=False)() as session:
            db = postgres_database(session)
            await db.faces.patch(face_id, FacePatchRequest(entity_id=entity_id), actor)
            return await db.sources.get_document(document.source_id)
    a, b = await asyncio.wait_for(asyncio.gather(
        edit(seeded.faces['issue8-face-3'], seeded.entities['nora']),
        edit(seeded.faces['issue8-face-4'], seeded.entities['emil']),
    ), timeout=10)
    assert a.last_touched_at != b.last_touched_at
    assert (await database.sources.get_document(document.source_id)).last_touched_at == max(a.last_touched_at, b.last_touched_at)
    assert await database.sources.delete_batch([document.source_id, seeded.pages['issue8-untouched']], context=actor) == 2
    assert await database.sources.get_document(document.source_id) is None
    assert await database.sources.get_page(seeded.pages['issue8-untouched']) is None
    assert (await database.sources.get_document(seeded.documents['issue8-mirror'])).last_touched_at is None


@pytest.mark.asyncio
async def test_issue8_direct_annotations_touch_only_document_and_preserve_recovery(seed_target, monkeypatch):
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.search import SearchDocumentsRequest
    from people_gator_api.schemas.enums import EntityLinkState
    from people_gator_api.schemas.mentions import TextMentionPatchRequest
    database, filesystem, _ = seed_target
    original_write = filesystem.write_bytes
    processed = None
    async def interrupted(key, content):
        nonlocal processed
        if key == preview.MANIFEST_KEY and b'issue8-direct-mention' in content and processed is None:
            document = next(item for item in DOCUMENTS if item.key == 'issue8-direct')
            processed = await database.sources.lookup_document(DocumentLookupRequest(library=document.library, document_id=document.document_id))
            raise OSError('direct checkpoint interrupted')
        await original_write(key, content)
    monkeypatch.setattr(filesystem, 'write_bytes', interrupted)
    with pytest.raises(OSError, match='checkpoint'):
        await preview.seed_preview(database, filesystem)
    result = await preview.seed_preview(database, filesystem)
    assert (await database.sources.get_document(processed.source_id)).last_touched_at == processed.last_touched_at
    filters = DocumentListFilter(source_id=[processed.source_id], entity_link_state=[EntityLinkState.manual])
    found = await database.sources.search_documents(SearchDocumentsRequest(query=QueryBase(text=['Emil Review']), filter_=filters, limit=10, return_total_count=True))
    assert found.total_count == 1 and found.items[0].entity_link_stats.mentions.manual == 1
    pages = await database.sources.list_pages(PageListRequest(limit=4, filter_=PageListFilter(library=[processed.library], document_id=[processed.document_id]), return_total_count=True))
    assert pages.total_count == 0
    # Verification changes source history; repeating verification preserves it.
    actor = GenericActor(user_id=result.users['reviewer'])
    await database.text_mentions.patch(result.mentions['issue8-direct-mention'], TextMentionPatchRequest(entity_link_state=EntityLinkState.verified), actor)
    verified = await database.sources.get_document(processed.source_id)
    await database.text_mentions.patch(result.mentions['issue8-direct-mention'], TextMentionPatchRequest(entity_link_state=EntityLinkState.verified), actor)
    assert (await database.sources.get_document(processed.source_id)).last_touched_at == verified.last_touched_at
    await preview.seed_preview(database, filesystem)
    assert (await database.sources.get_document(processed.source_id)).last_touched_at == verified.last_touched_at


@pytest.mark.asyncio
async def test_issue8_source_only_actor_and_key_references(seed_target):
    from people_gator_api.schemas.users import UserCreateRequest
    from people_gator_api.schemas.api_keys import APIKeyCreateRequest
    from people_gator_api.schemas.sources import ImageCreateRequest
    from people_gator_api.schemas.faces import FaceCreateRequest
    from people_gator_api.seeding.fixtures import Face
    from people_gator_api.seeding.media import face_box, face_keypoints
    from people_gator_api.services.auth_service import AuthContext
    database, _, _ = seed_target
    user = await database.users.get_or_create(UserCreateRequest(display_name='Source only actor', external_subject='source-only-actor', external_issuer='issue8-test', is_active=True))
    other = await database.users.get_or_create(UserCreateRequest(display_name='Other actor', external_subject='other-actor', external_issuer='issue8-test', is_active=True))
    image, _ = await database.sources.get_or_create_image(ImageCreateRequest(url='https://preview.invalid/source-only.png'))
    actor = GenericActor(user_id=user.user_id)
    face = await database.faces.create(FaceCreateRequest(source_id=image.source_id, confidence=0.9, bounding_box=face_box(Face("source-ref", None, 0, 0)), keypoints=face_keypoints(Face("source-ref", None, 0, 0))), actor)
    await database.faces.delete(face.detection_id, context=actor)
    # No owned face, entity or key remains; source processing alone protects U.
    with pytest.raises(ValueError, match='referenced'):
        await database.users.delete(user.user_id)
    key = await database.api_keys.get_or_create(APIKeyCreateRequest(identifier='source-only-key', display_name='Historical source key', user_id=user.user_id))
    key_actor = AuthContext(user_id=user.user_id, user=user, api_key_id=key.api_key_id, authentication_method='api_key', scopes=set())
    face = await database.faces.create(FaceCreateRequest(source_id=image.source_id, confidence=0.9, bounding_box=face_box(Face("source-ref", None, 0, 0)), keypoints=face_keypoints(Face("source-ref", None, 0, 0))), key_actor)
    await database.faces.delete(face.detection_id, context=key_actor)
    with pytest.raises(ValueError, match='referenced API key'):
        await database.api_keys.get_or_create(APIKeyCreateRequest(identifier='source-only-key', display_name='Renamed key', user_id=other.user_id))
    assert (await database.sources.get_image(image.source_id)).last_touched_by_api_key_id == key.api_key_id


@pytest.mark.asyncio
async def test_issue8_migration_preserves_sources_without_fabricating_history(seed_target):
    from sqlalchemy import inspect
    from people_gator_api.persistence.postgres.bootstrap import adopt_bootstrap_schema
    from people_gator_api.schemas.sources import document_url, page_url
    from people_gator_api.persistence.postgres.schema import validate_schema, SchemaValidationError
    _, _, engine = seed_target
    document_id, page_id = uuid.uuid4(), uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(3)]
    def old_schema(connection):
        config = migration_config(); config.attributes['connection'] = connection
        command.downgrade(config, 'd34a021b0004')
        for source_id, kind, url in zip(ids, ['document','page','image'], [document_url('historical', document_id), page_url('historical',document_id,page_id), 'https://preview.invalid/historical.png']):
            connection.execute(text('INSERT INTO pg_demo_sources(id, source_type, url) VALUES (:id,:kind,:url)'), {'id':source_id,'kind':kind,'url':url})
        connection.execute(text('INSERT INTO pg_demo_documents(id,library,document_id,name) VALUES (:id, :library, :document_id, :name)'), {'id':ids[0], 'library':'historical', 'document_id':document_id, 'name':'Příběhy history'})
        connection.execute(text('INSERT INTO pg_demo_pages(id,library,document_id,page_id) VALUES (:id, :library, :document_id, :page_id)'), {'id':ids[1], 'library':'historical', 'document_id':document_id, 'page_id':page_id})
        connection.execute(text('INSERT INTO pg_demo_images(id) VALUES (:id)'), {'id':ids[2]})
        assert adopt_bootstrap_schema(connection, config) == 'd34a021b0004'
        command.upgrade(config, 'head')
        validate_schema(connection)
        inspector = inspect(connection)
        fields = {item['name'] for item in inspector.get_columns('pg_demo_sources')}
        assert {'last_touched_at','last_touched_by_user_id','last_touched_by_api_key_id'} <= fields
        for table in ['pg_demo_documents','pg_demo_pages','pg_demo_images']:
            assert not any(item['name'].startswith('last_touched') for item in inspector.get_columns(table))
        assert connection.execute(text('SELECT last_touched_at,last_touched_by_user_id,last_touched_by_api_key_id FROM pg_demo_sources')).all() == [(None,None,None)]*3
        assert connection.scalar(text('SELECT name FROM pg_demo_documents')) == 'Příběhy history'
        assert connection.scalar(text('SELECT name_normalized FROM pg_demo_documents')) == 'pribehy history'
    async with engine.begin() as connection:
        await connection.run_sync(old_schema)
    async with engine.connect() as connection:
        async with connection.begin():
            await connection.execute(text('ALTER TABLE pg_demo_sources DROP CONSTRAINT ck_pg_demo_sources_touch'))
            with pytest.raises(SchemaValidationError, match='consistency'):
                await connection.run_sync(validate_schema)
            await connection.rollback()


@pytest.mark.asyncio
async def test_issue8_png_upgrade_preserves_source_history_and_reviewed_media(seed_target):
    from people_gator_api.seeding.fixtures import ISSUE8_IMAGE_URL
    from people_gator_api.seeding.media import page_image
    from people_gator_api.schemas.sources import ImageLookupRequest
    from people_gator_api.media.image_content import image_content_key
    database, filesystem, _ = seed_target
    await preview.seed_preview(database, filesystem)
    image = await database.sources.lookup_image(ImageLookupRequest(url=ISSUE8_IMAGE_URL))
    key = image_content_key(ISSUE8_IMAGE_URL)
    legacy = page_image(PAGES[0], next(item for item in DOCUMENTS if item.key == 'issue8-search'))
    await filesystem.write_bytes(key, legacy)
    await preview.seed_preview(database, filesystem)
    repaired = await filesystem.read_bytes(key)
    assert Image.open(io.BytesIO(repaired)).format == 'PNG'
    assert repaired != legacy
    assert (await database.sources.get_image(image.source_id)).last_touched_at == image.last_touched_at
    edited = io.BytesIO()
    Image.new('RGB', (800,1100), '#bb88cc').save(edited, 'PNG')
    await filesystem.write_bytes(key, edited.getvalue())
    await preview.seed_preview(database, filesystem)
    assert await filesystem.read_bytes(key) == edited.getvalue()
    assert (await database.sources.get_image(image.source_id)).last_touched_at == image.last_touched_at


@pytest.mark.asyncio
async def test_media_upload_sandbox_is_usable_and_preserves_replacements(seed_target, monkeypatch):
    from people_gator_api.media.page_image import put_page_image
    from people_gator_api.media.page_layout import put_page_layout
    from people_gator_api.settings import PageImageCacheSettings

    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    document = await database.sources.get_document(first.documents["issue10-media"])
    assert document.name == "Media upload sandbox"
    pages = [await database.sources.get_page(first.pages[f"media-upload-{i}"]) for i in (1, 2)]
    originals = []
    for page in pages:
        assert page.document_id == document.document_id and page.library == document.library
        assert page.entity_link_stats.faces.total == page.entity_link_stats.mentions.total == 0
        assert page.last_touched_at is None
        image = await get_page_image(page.library, page.document_id, page.page_id)
        layout = await get_page_layout(page.library, page.document_id, page.page_id)
        with Image.open(io.BytesIO(image.content)) as scan:
            assert tuple(reversed(scan.size)) == layout.page_size
        originals.append((image.content, layout))
    assert urlsplit(first.filter_examples["media-upload"]).path == (
        f"/libraries/{document.library}/documents/{document.document_id}/pages/{pages[0].page_id}"
    )

    # Upload real replacements through the same media services used by the routes.
    monkeypatch.setattr(settings, "page_image_cache", PageImageCacheSettings(widths=[64]))
    content = io.BytesIO()
    Image.new("RGB", (800, 1100), "blue").save(content, "JPEG")
    page = pages[0]
    size = await put_page_image(page.library, page.document_id, page.page_id, content.getvalue())
    layout = originals[0][1].model_copy(update={"id": "reviewed-upload"})
    await put_page_layout(page.library, page.document_id, page.page_id, layout)
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    fetched = await get_page_image(page.library, page.document_id, page.page_id)
    assert fetched.content == content.getvalue() and len(fetched.content) == size
    assert await get_page_layout(page.library, page.document_id, page.page_id) == layout
    derivative = await get_page_image(page.library, page.document_id, page.page_id, max_width=64)
    with Image.open(io.BytesIO(derivative.content)) as scan:
        assert scan.width == 64
        red, _, blue = scan.getpixel((0, 0))
        assert blue > red
    other = pages[1]
    assert (await get_page_image(other.library, other.document_id, other.page_id)).content == originals[1][0]
    assert await get_page_layout(other.library, other.document_id, other.page_id) == originals[1][1]
    assert (await database.sources.get_page(page.source_id)).last_touched_at is None


@pytest.mark.asyncio
async def test_scan_toolbar_examples_filter_real_evidence_and_preserve_reviews(seed_target):
    from itertools import combinations

    from people_gator_api.schemas.enums import EntityLinkState as State
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionListFilter, TextMentionPatchRequest
    from people_gator_api.schemas.missing import MISSING

    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    expected = {
        'links-1': {'auto': State.automatic, 'manual': State.manual},
        'links-2': {'verified': State.verified, 'unassigned': None},
    }
    for example, page_key, selected in (
        ('scan-toolbar', 'links-2', []),
        ('scan-toolbar-union', 'links-1', [State.automatic, State.manual]),
        ('scan-toolbar-assigned', 'links-2', list(State)),
    ):
        link = urlsplit(first.filter_examples[example])
        assert parse_qs(link.query).get('link_state', []) == selected
        page = await database.sources.get_page(first.pages[page_key])
        assert link.path == (
            f'/libraries/{page.library}/documents/{page.document_id}/pages/{page.page_id}'
        )
        image = await get_page_image(page.library, page.document_id, page.page_id)
        with Image.open(io.BytesIO(image.content)) as scan:
            assert scan.size == (800, 1100)
        for size in range(4):
            for states in combinations(list(State), size):
                matching = {key for key, state in expected[page_key].items()
                            if not states or state in states}
                faces = await database.faces.list(FaceListRequest(
                    limit=100, filter_=FaceListFilter(
                        source_id=[page.source_id], entity_link_state=list(states) if states else MISSING,
                    ),
                ))
                mentions = await database.text_mentions.list(TextMentionListRequest(
                    limit=100, filter_=TextMentionListFilter(
                        source_id=[page.source_id], entity_link_state=list(states) if states else MISSING,
                    ),
                ))
                assert {face.detection_id for face in faces.items} == {
                    first.faces['links-' + key] for key in matching
                }
                assert {mention.mention_id for mention in mentions.items} == {
                    first.mentions['links-' + key + '-mention'] for key in matching
                }
                spans = await get_text_mention_spans(
                    database, page.source_id, library=page.library,
                    document_id=page.document_id, page_id=page.page_id,
                    entity_link_state=list(states) if states else MISSING,
                )
                # OCR overlays represent assigned mentions; unassigned records
                # remain available through the mention repository.
                assert {span.mention_id for span in spans} == {
                    first.mentions['links-' + key + '-mention']
                    for key in matching if expected[page_key][key] is not None
                }

    actor = GenericActor(user_id=first.users['reviewer'])
    reviewed_face = await database.faces.patch(
        first.faces['links-verified'], FacePatchRequest(entity_link_state=State.manual), actor,
    )
    reviewed_mention = await database.text_mentions.patch(
        first.mentions['links-verified-mention'],
        TextMentionPatchRequest(entity_link_state=State.manual), actor,
    )
    page_before = await database.sources.get_page(first.pages['links-2'])
    document_before = await database.sources.get_document(first.documents['link-states'])
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    assert await database.faces.get(reviewed_face.detection_id) == reviewed_face
    assert await database.text_mentions.get(reviewed_mention.mention_id) == reviewed_mention
    assert await database.sources.get_page(page_before.source_id) == page_before
    assert await database.sources.get_document(document_before.source_id) == document_before


@pytest.mark.asyncio
async def test_annotation_filter_parity_and_creation_preservation(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionListFilter
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.enums import EntityLinkState

    database, filesystem, _ = seed_target
    result = await preview.seed_preview(database, filesystem)
    person = result.entities['provenance-review']
    authority = await database.faces.get(result.faces['provenance-authority'])
    assert authority.entity_link_state == EntityLinkState.verified
    assert authority.created_by_api_key_id == result.api_keys['importer']
    assert authority.last_touched_by_user_id == result.users['reviewer']
    assert authority.last_touched_by_api_key_id is None
    assert authority.last_touched_at > authority.created_at
    identity = await database.entities.get(person)
    assert identity.created_at < authority.last_touched_at

    criteria = dict(entity_link_state=['manual', 'verified'],
                    evidence_library=['preview-mzk'], document_source_id=[result.documents['provenance-a']],
                    evidence_touched_by_user_id=[result.users['reviewer']],
                    evidence_touched_from=authority.last_touched_at,
                    evidence_touched_to=authority.last_touched_at)
    faces = await database.faces.list(FaceListRequest(filter_=FaceListFilter(entity_id=[person], **criteria), limit=1, return_total_count=True))
    assert [f.detection_id for f in faces.items] == [authority.detection_id]
    assert faces.total_count == 1 and faces.cursor is None
    entities = await database.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(**criteria), return_total_count=True))
    assert [e.entity_id for e in entities.items] == [person]
    docs = await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(**criteria), return_total_count=True))
    assert [d.source_id for d in docs.items] == [result.documents['provenance-a']]
    # Manual evidence is in the other document: unrelated witnesses cannot combine.
    impossible = {**criteria, 'entity_link_state': ['manual']}
    assert not (await database.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(**impossible)))).items
    assert not (await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(**impossible)))).items
    mentions = await database.text_mentions.list(TextMentionListRequest(limit=100, filter_=TextMentionListFilter(
        entity_id=[person], evidence_touched_by_user_id=[result.users['reviewer']]), return_total_count=True))
    assert [m.mention_id for m in mentions.items] == [result.mentions['provenance-mention-verified']]
    before = authority.model_dump()
    await preview.seed_preview(database, filesystem)
    assert (await database.faces.get(authority.detection_id)).model_dump() == before
    # Identical verification preserves time and attribution; a material JWT edit clears the key.
    reviewer = GenericActor(user_id=result.users['reviewer'])
    unchanged = await database.faces.patch(authority.detection_id, FacePatchRequest(entity_link_state='verified'), reviewer)
    assert unchanged.last_touched_at == authority.last_touched_at
    automatic = await database.faces.get(result.faces['provenance-auto'])
    assert automatic.last_touched_by_api_key_id == result.api_keys['importer']
    changed = await database.faces.patch(automatic.detection_id, FacePatchRequest(entity_link_state='manual'), reviewer)
    assert changed.last_touched_by_api_key_id is None
    assert changed.last_touched_at > automatic.last_touched_at
    assert changed.created_at == automatic.created_at
    assert changed.created_by_api_key_id == automatic.created_by_api_key_id


@pytest.mark.asyncio
async def test_annotation_metadata_migration_keeps_historical_unknown(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter
    db, filesystem, engine = seed_target
    seed = await preview.seed_preview(db, filesystem)
    detection_id = seed.faces['provenance-authority']
    # End repository reads before the separate DDL connection takes table locks.
    await db.faces._session.rollback()
    async with engine.begin() as connection:
        def migrate(sync):
            config = migration_config()
            config.attributes['connection'] = sync
            command.downgrade(config, 'd34a021b0006')
            command.upgrade(config, 'head')
            command.upgrade(config, 'head')
        await connection.run_sync(migrate)
    await validate_postgres_schema(engine)
    face = await db.faces.get(detection_id)
    assert face.entity_link_state.value == 'verified'
    assert face.last_touched_at is None and face.created_at is None
    matches = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        detection_id=[detection_id])))
    assert [item.detection_id for item in matches.items] == [detection_id]
    matches = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        detection_id=[detection_id], evidence_touched_from='2000-01-01T00:00:00Z')))
    assert not matches.items
    await preview.seed_preview(db, filesystem)
    assert (await db.faces.get(detection_id)).last_touched_at is None


@pytest.mark.asyncio
async def test_evidence_pagination_counts_and_similarity_witnesses(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    person = seed.entities['provenance-review']
    ids, cursor = [], None
    while True:
        page = await db.faces.list(FaceListRequest(limit=1, return_total_count=True, cursor=cursor,
            filter_=FaceListFilter(entity_id=[person])))
        assert page.total_count == 4
        assert all(face.entity_id == person for face in page.items)
        ids.extend(face.detection_id for face in page.items)
        cursor = page.cursor
        if cursor is None:
            break
    assert len(ids) == len(set(ids)) == 4
    found = await db.entities.search(SearchEntitiesRequest(limit=100, query=QueryBase(
        face_id=[seed.faces['provenance-auto']], face_embedding_model=MODEL),
        filter_=EntityListFilter(evidence_touched_by_user_id=[seed.users['reviewer']], document_source_id=[seed.documents['provenance-a']])))
    assert [item.entity_id for item in found.items] == [person]
    assert found.items[0].matched_detection_ids == [seed.faces['provenance-authority']]


@pytest.mark.asyncio
async def test_page_activity_example_distinguishes_annotation_editors(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionListFilter
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    assert parse_qs(urlsplit(seed.filter_examples['page-activity']).query) == {'panel':['activity']}
    page_id = seed.pages['provenance-a-1']
    faces = (await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(source_id=[page_id])))).items
    mentions = (await db.text_mentions.list(TextMentionListRequest(limit=100, filter_=TextMentionListFilter(source_id=[page_id])))).items
    assert len(faces) == 2 and len(mentions) == 1
    edits = [*faces,*mentions]
    assert sum(item.last_touched_by_user_id == seed.users['importer'] for item in edits) == 2
    assert sum(item.last_touched_by_user_id == seed.users['reviewer'] for item in edits) == 1
    assert all(item.last_touched_at for item in edits)
    reviewer_faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(source_id=[page_id], evidence_touched_by_user_id=[seed.users['reviewer']])))
    assert [item.detection_id for item in reviewer_faces.items] == [seed.faces['provenance-authority']]


@pytest.mark.asyncio
async def test_card_and_statistics_entry_points_resolve_attributed_evidence_and_media(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    cards = urlsplit(seed.filter_examples['person-evidence-cards'])
    person_id = seed.entities['provenance-review']
    comparison = urlsplit(seed.filter_examples['person-face-style-comparison'])
    assert comparison.path == cards.path
    assert parse_qs(comparison.query) == {'tab': ['discover']}
    assert cards.path == f'/people/{person_id}'
    assert parse_qs(cards.query) == {
        'origin_matched_face': [str(seed.faces['provenance-authority'])],
        'origin_text': ['Irena'],
    }
    faces = (await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(entity_id=[person_id]),
    ))).items
    assert {face.entity_link_state.value for face in faces} == {'automatic', 'manual', 'verified'}
    states_example = urlsplit(seed.filter_examples['linked-face-states'])
    assert states_example.path == cards.path
    assert parse_qs(states_example.query) == {'link_state': ['automatic', 'manual', 'verified']}
    filtered_faces = (await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(entity_id=[person_id],
            entity_link_state=parse_qs(states_example.query)['link_state']),
    ))).items
    assert {face.detection_id for face in filtered_faces} == {face.detection_id for face in faces}
    assert all(face.entity_id == person_id for face in filtered_faces)
    assert {face.last_touched_by_user_id for face in faces} == {
        seed.users['importer'], seed.users['reviewer'],
    }
    for face in faces:
        editor = await db.users.get(face.last_touched_by_user_id)
        assert editor.display_name in {'Preview reviewer', 'Preview face importer'}
        assert face.confidence is not None and 0 <= face.confidence <= 1
        assert face.last_touched_at is not None
        page = await db.sources.get_page(face.source_id)
        assert page is not None and page.library and page.document_id and page.page_id
        image = await get_page_image(page.library, page.document_id, page.page_id)
        with Image.open(io.BytesIO(image.content)) as scan:
            assert scan.size == (800, 1100)

    statistics = urlsplit(seed.filter_examples['page-statistics'])
    page = await db.sources.get_page(seed.pages['links-2'])
    document = await db.sources.get_document(seed.documents['link-states'])
    assert statistics.path == f'/libraries/{page.library}/documents/{page.document_id}/pages/{page.page_id}'
    assert parse_qs(statistics.query) == {'panel': ['statistics']}
    assert page.entity_link_stats.faces.verified == 1
    assert page.entity_link_stats.faces.unassigned == 1
    assert document.entity_link_stats.faces.total == 4
    assert document.entity_link_stats.mentions.total == 4
    rerun = await preview.seed_preview(db, filesystem)
    assert rerun == seed
    for face in faces:
        assert await db.faces.get(face.detection_id) == face


@pytest.mark.asyncio
async def test_shared_filter_navigation_uses_current_annotation_key(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    example = urlsplit(seed.filter_examples['shared-filter-navigation'])
    query = parse_qs(example.query)
    assert example.path == '/people'
    assert query == {'q': ['Irena'], 'evidence_key': [str(seed.api_keys['importer'])]}
    people = await db.entities.search(SearchEntitiesRequest(limit=100,
        query=QueryBase(text=query['q']),
        filter_=EntityListFilter(evidence_touched_by_api_key_id=query['evidence_key']),
    ))
    assert [person.entity_id for person in people.items] == [seed.entities['provenance-review']]
    faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        entity_id=[people.items[0].entity_id], evidence_touched_by_api_key_id=query['evidence_key'],
    )))
    assert seed.faces['provenance-auto'] in {face.detection_id for face in faces.items}
    changed = await db.entities.search(SearchEntitiesRequest(limit=100,
        query=QueryBase(text=query['q']),
        filter_=EntityListFilter(evidence_touched_by_api_key_id=[seed.api_keys['ocr']]),
    ))
    assert not changed.items
    cleared = await db.faces.list(FaceListRequest(limit=100,
        filter_=FaceListFilter(entity_id=[seed.entities['provenance-review']]),
    ))
    assert len(cleared.items) > len(faces.items)
    before = {face.detection_id: face for face in cleared.items}
    for _ in range(2):
        rerun = await preview.seed_preview(db, filesystem)
        assert rerun.filter_examples['shared-filter-navigation'] == seed.filter_examples['shared-filter-navigation']
        for detection_id, face in before.items():
            assert await db.faces.get(detection_id) == face


@pytest.mark.asyncio
async def test_scan_assignment_search_finds_people_elsewhere_and_preserves_review(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    query = parse_qs(urlsplit(seed.filter_examples['scan-assignment-search']).query)
    assert set(query) == {'library', 'document'}
    pages = await db.sources.list_pages(PageListRequest(limit=100, filter_=PageListFilter(
        library=query['library'], document_id=query['document'],
    )))
    assert [page.source_id for page in pages.items] == [seed.pages['provenance-a-1']]
    source_id = pages.items[0].source_id
    on_page = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        source_id=[source_id],
    )))
    assert seed.entities['ada'] not in {face.entity_id for face in on_page.items}
    candidates = await db.entities.search(SearchEntitiesRequest(
        query=QueryBase(text=['Ada Novak']), limit=100,
    ))
    assert seed.entities['ada'] in {person.entity_id for person in candidates.items}
    edited = await db.faces.patch(seed.faces['provenance-auto'], FacePatchRequest(
        entity_id=seed.entities['ada'], entity_link_state='manual',
    ), GenericActor(user_id=seed.users['reviewer']))
    assert edited.source_id == source_id and edited.entity_id == seed.entities['ada']
    for _ in range(2):
        rerun = await preview.seed_preview(db, filesystem)
        assert rerun.filter_examples['scan-assignment-search'] == seed.filter_examples['scan-assignment-search']
        assert await db.faces.get(edited.detection_id) == edited
    page = pages.items[0]
    image = await get_page_image(page.library, page.document_id, page.page_id)
    assert image.content


@pytest.mark.asyncio
async def test_person_face_review_preserves_verified_and_unassigned_edits_on_rerun(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter, FacePatchBatchItem

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    person_id = seed.entities['provenance-review']
    assert seed.filter_examples['person-face-review'] == f'/people/{person_id}'
    person = await db.entities.get(person_id)
    assert person.created_at is not None and person.last_touched_at is not None
    actor = GenericActor(user_id=seed.users['reviewer'])
    automatic = await db.faces.get(seed.faces['provenance-auto'])
    manual = await db.faces.get(seed.faces['provenance-manual'])
    assert automatic.entity_link_state.value == 'automatic'
    assert manual.entity_link_state.value == 'manual'
    assert (await db.faces.get(seed.faces['provenance-authority'])).entity_link_state.value == 'verified'
    updated = await db.faces.patch_batch([
        FacePatchBatchItem(detection_id=automatic.detection_id, entity_link_state='verified'),
        FacePatchBatchItem(detection_id=manual.detection_id, entity_id=None, entity_link_state=None),
    ], actor)
    verified, unassigned = updated
    reviewed_person = await db.entities.get(person_id)
    assert reviewed_person.created_at == person.created_at
    assert reviewed_person.created_by_user_id == person.created_by_user_id
    assert verified.entity_id == person_id and verified.entity_link_state.value == 'verified'
    assert unassigned.entity_id is None and unassigned.entity_link_state is None
    assert verified.last_touched_by_user_id == actor.user_id
    assert unassigned.last_touched_by_user_id == actor.user_id
    assert verified.created_at == automatic.created_at
    assert unassigned.created_at == manual.created_at
    for _ in range(2):
        rerun = await preview.seed_preview(db, filesystem)
        assert rerun.filter_examples['person-face-review'] == seed.filter_examples['person-face-review']
        assert await db.faces.get(verified.detection_id) == verified
        assert await db.faces.get(unassigned.detection_id) == unassigned
        assert await db.entities.get(person_id) == reviewed_person
    linked = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(entity_id=[person_id])))
    assert verified.detection_id in {face.detection_id for face in linked.items}
    assert unassigned.detection_id not in {face.detection_id for face in linked.items}
    for face in updated:
        page = await db.sources.get_page(face.source_id)
        image = await get_page_image(page.library, page.document_id, page.page_id)
        assert image.content


@pytest.mark.asyncio
async def test_creation_and_reviews_survive_metadata_cleanup_upgrade(seed_target):
    from sqlalchemy import inspect

    db, filesystem, engine = seed_target
    seed = await preview.seed_preview(db, filesystem)
    before_face = await db.faces.get(seed.faces['provenance-authority'])
    before_person = await db.entities.get(seed.entities['provenance-review'])
    await db.faces._session.rollback()
    async with engine.begin() as connection:
        def upgrade_retained_preview(sync):
            config = migration_config()
            config.attributes['connection'] = sync
            command.downgrade(config, 'd34a021b0007')
            for table in ('pg_demo_entities', 'pg_demo_image_occurrences', 'pg_demo_text_mentions'):
                sync.execute(text(f"UPDATE {table} SET provenance = '{{\"discarded\": true}}'::jsonb"))
            command.upgrade(config, 'head')
            command.upgrade(config, 'head')
            inspector = inspect(sync)
            for table in ('pg_demo_entities', 'pg_demo_image_occurrences', 'pg_demo_text_mentions'):
                columns = {item['name'] for item in inspector.get_columns(table)}
                assert columns >= {'created_at', 'created_by_user_id', 'created_by_api_key_id'}
                assert not columns & {'provenance'}
        await connection.run_sync(upgrade_retained_preview)
    await validate_postgres_schema(engine)
    assert await db.faces.get(before_face.detection_id) == before_face
    assert await db.entities.get(before_person.entity_id) == before_person
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        assert await db.faces.get(before_face.detection_id) == before_face
        assert await db.entities.get(before_person.entity_id) == before_person


@pytest.mark.asyncio
async def test_annotation_editor_example_uses_same_user_and_key_and_preserves_creation(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    example = urlsplit(seed.filter_examples['annotation-editor-filters'])
    query = parse_qs(example.query)
    assert example.path == f"/people/{seed.entities['provenance-review']}"
    assert query == {
        'evidence_user': [str(seed.users['importer'])],
        'evidence_key': [str(seed.api_keys['importer'])],
    }
    matches = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        entity_id=[seed.entities['provenance-review']],
        evidence_touched_by_user_id=query['evidence_user'],
        evidence_touched_by_api_key_id=query['evidence_key'],
    )))
    assert {face.detection_id for face in matches.items} == {
        seed.faces['provenance-auto'], seed.faces['provenance-manual'], seed.faces['provenance-unknown'],
    }
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        for face in matches.items:
            assert await db.faces.get(face.detection_id) == face


@pytest.mark.asyncio
async def test_document_navigation_keeps_unannotated_pages_and_explicit_filters(seed_target):
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    example = urlsplit(seed.filter_examples['document-pages-without-annotations'])
    assert example.path == '/documents'
    assert parse_qs(example.query) == {'q': ['Příběhy archivářů']}
    document = await db.sources.get_document(seed.documents['issue8-search'])
    scope = dict(library=[document.library], document_id=[document.document_id])
    pages, cursor = [], None
    while True:
        result = await db.sources.list_pages(PageListRequest(limit=2, cursor=cursor,
            return_total_count=True, filter_=PageListFilter(**scope)))
        assert result.total_count == 6
        pages.extend(result.items)
        cursor = result.cursor
        if cursor is None:
            break
    assert len({page.source_id for page in pages}) == 6
    untouched = next(page for page in pages if page.source_id == seed.pages['issue8-untouched'])
    assert untouched.entity_link_stats.faces.total == 0
    assert untouched.entity_link_stats.mentions.total == 0
    filtered = await db.sources.list_pages(PageListRequest(limit=100,
        return_total_count=True, filter_=PageListFilter(**scope,
            evidence_touched_by_user_id=[seed.users['importer']])))
    assert filtered.total_count == 4
    assert untouched.source_id not in {page.source_id for page in filtered.items}
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        assert await db.sources.get_page(untouched.source_id) == untouched
