"""Exercise the preview dataset against migrated PostgreSQL and real local media."""

from collections.abc import Callable, Coroutine
import io
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
from alembic import command
from PIL import Image
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from people_gator_api.filesystem.contracts import Filesystem
from people_gator_api.filesystem.local import LocalFilesystem
from people_gator_api.persistence.contracts import Database
from people_gator_api.media.aligned_face_crop import get_aligned_face_crop
from people_gator_api.media.page_image import get_page_image
from people_gator_api.media.page_layout import get_page_layout
from people_gator_api.media.errors import SourceResolutionError
from people_gator_api.media.text_mention_spans import get_text_mention_spans
from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.auth import TokenResponse
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.schema import (
    migration_config,
    validate_postgres_schema,
)
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.users import UserResponse
from people_gator_api.schemas.entities import (
    EntityResponse,
    EntityListFilter,
    EntityListRequest,
    EntityPatchRequest,
)
from people_gator_api.schemas.faces import FaceResponse, FaceCreateRequest, FaceListFilter, FaceListRequest, FacePatchRequest
from people_gator_api.schemas.mentions import TextMentionListRequest, TextMentionPatchRequest
from people_gator_api.schemas.sources import (
    PageResponse,
    DocumentListRequest,
    DocumentLookupRequest,
    GenericSourceLookupRequest,
    PageListFilter,
    PageListRequest,
    PageLookupRequest,
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
    PAGE_GALLERY_MISSING_MEDIA,
    PAGE_GALLERY_PAGES,
    PAGES,
    SECOND_MODEL,
    Person,
)
from people_gator_api.services import filesystem_service
from people_gator_api.settings import settings


type SeedTarget = tuple[Database, LocalFilesystem, AsyncEngine]


@pytest_asyncio.fixture
async def seed_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, migrated_postgres: AsyncEngine,
) -> AsyncIterator[SeedTarget]:
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
    assert await counts(database) == (37, 119, 75)
    assert len(result.documents) == 50 and len(result.pages) == 106
    assert len(result.users) == 5 and len(result.api_keys) == 3

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
            {"actions", "emil", "ada-candidate", "discovery", "discovery-face", "discovery-name", "discovery-alias", "shared-hana", "review-candidate"},

        ),
        (EntityListFilter(has_detections=False, has_mentions=True), {"nora", "shared-ivo", "deactivated-olga", *(f"pagination-{i}" for i in range(1, 15))}),
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
        if not page.has_image:
            continue  # Missing-media navigation is covered by the page gallery test.
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
            if spec.coincident_keypoints:
                with pytest.raises(SourceResolutionError) as error:
                    await get_aligned_face_crop(
                        result.users["reviewer"], face, source, max_width=256
                    )
                assert error.value.status_code == 422
                assert error.value.code == "invalid_face_keypoints"
                continue
            crop = await get_aligned_face_crop(
                result.users["reviewer"], face, source, max_width=256
            )
            with Image.open(io.BytesIO(crop.content)) as image:
                assert 0 < image.width <= 256 and image.width == image.height


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_face", ["alignment-coincident", "alignment-valid"])
async def test_alignment_fixture_additive_recovery_http_and_review_preservation(
    seed_target: tuple[Database, Filesystem, AsyncEngine],
    monkeypatch: pytest.MonkeyPatch,
    failed_face: str,
) -> None:
    import asyncio
    import httpx
    from fastapi import FastAPI
    from people_gator_api.media import aligned_face_crop
    from people_gator_api.routes.v1 import router
    from people_gator_api.services import auth_service, database_service
    from people_gator_api.services.auth_service import AuthContext

    database: Database
    filesystem: Filesystem
    _engine: AsyncEngine
    database, filesystem, _engine = seed_target
    # Upgrade a retained preview without touching its existing fixture identities.
    with monkeypatch.context() as legacy:
        for name in ("DOCUMENTS", "PAGES"):
            legacy.setattr(preview, name, tuple(
                item for item in getattr(preview, name)
                if not item.key.startswith("alignment")
            ))
        old: preview.SeedResult = await preview.seed_preview(database, filesystem)
    old_face: FaceResponse | None = await database.faces.get(old.faces["ada-portrait"])
    assert old_face is not None
    original_write: Callable[[str, bytes], Coroutine[object, object, None]] = filesystem.write_bytes
    interrupted_id: uuid.UUID | None = None

    async def interrupt_checkpoint(key: str, content: bytes) -> None:
        nonlocal interrupted_id
        if key == preview.MANIFEST_KEY and interrupted_id is None:
            identifier: str | None = json.loads(content)["faces"].get(failed_face)
            if identifier is not None:
                interrupted_id = uuid.UUID(identifier)
                raise OSError("interrupted alignment checkpoint")
        await original_write(key, content)

    monkeypatch.setattr(filesystem, "write_bytes", interrupt_checkpoint)
    with pytest.raises(OSError, match="interrupted alignment"):
        await preview.seed_preview(database, filesystem)
    seed: preview.SeedResult = await preview.seed_preview(database, filesystem)
    assert seed.faces[failed_face] == interrupted_id
    for name in ("entities", "documents", "pages", "faces", "mentions"):
        assert getattr(old, name).items() <= getattr(seed, name).items()
    assert await database.faces.get(old_face.detection_id) == old_face
    faces: list[FaceResponse] = (await database.faces.list(FaceListRequest(
        filter_=FaceListFilter(source_id=[seed.pages["alignment-1"]]), limit=100,
    ))).items
    assert {face.detection_id for face in faces} == {
        seed.faces["alignment-coincident"], seed.faces["alignment-valid"],
    }
    invalid: FaceResponse | None = await database.faces.get(seed.faces["alignment-coincident"])
    assert invalid is not None
    assert len(invalid.keypoints) == 5
    assert len({point.type for point in invalid.keypoints}) == 5
    assert len({(point.x, point.y) for point in invalid.keypoints}) == 1
    for point in invalid.keypoints:
        assert 0 <= point.x < 800 and 0 <= point.y < 1100
    page_before: PageResponse | None = await database.sources.get_page(invalid.source_id)
    assert page_before is not None
    user: UserResponse | None = await database.users.get(seed.users["reviewer"])
    assert user is not None
    actor: AuthContext = AuthContext(
        user_id=seed.users["reviewer"],
        user=user,
        scopes={"people-gator:browse"}, authentication_method="bearer",
    )
    app: FastAPI = FastAPI()
    app.include_router(router)

    def get_database() -> Database:
        return database

    def get_auth_context() -> AuthContext:
        return actor

    app.dependency_overrides[database_service.get_database] = get_database
    app.dependency_overrides[auth_service.get_auth_context] = get_auth_context
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test",
    ) as client:
        for enabled in (False, True):
            monkeypatch.setattr(settings.aligned_face_crop, "cache_enabled", enabled)
            response: httpx.Response = await client.get(seed.filter_examples["alignment-coincident-crop"])
            assert response.status_code == 422
            assert response.json()["detail"]["code"] == "invalid_face_keypoints"
        response = await client.get(seed.filter_examples["alignment-valid-crop"])
        assert response.status_code == 200 and response.headers["X-Cache"] == "MISS"
        assert response.headers["content-type"] == "image/jpeg"
        with Image.open(io.BytesIO(response.content)) as image:
            image.load()
            assert 0 < image.width <= 256 and image.width == image.height
        await asyncio.gather(*list(aligned_face_crop._background_cache_writes))
        hit: httpx.Response = await client.get(seed.filter_examples["alignment-valid-crop"])
        assert hit.headers["X-Cache"] == "HIT" and hit.content == response.content
        for width in (0, -1):
            response = await client.get(
                f"/api/v1/faces/{invalid.detection_id}/aligned_crop?max_width={width}"
            )
            assert response.status_code == 422
            assert response.json()["detail"][0]["type"] == "greater_than"
    assert await database.faces.get(invalid.detection_id) == invalid
    assert await database.sources.get_page(invalid.source_id) == page_before

    reviewed: FaceResponse | None = await database.faces.patch(
        invalid.detection_id, FacePatchRequest(entity_id=seed.entities["lenka"]), actor,
    )
    assert reviewed is not None
    reviewed_person: EntityResponse | None = await database.entities.get(seed.entities["lenka"])
    assert reviewed_person is not None
    for _ in range(2):
        assert await preview.seed_preview(database, filesystem) == seed
        assert await database.faces.get(invalid.detection_id) == reviewed
        assert await database.entities.get(reviewed_person.entity_id) == reviewed_person
    assert await counts(database) == (37, 119, 75)


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
    assert await counts(database) == (37, 119, 75)

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
    assert await counts(database) == (38, 119, 75)



@pytest.mark.asyncio
@pytest.mark.parametrize("failed_checkpoint", [1, 7, 15])
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
    assert len(result.entities) == 37 and len(result.faces) == 119
    assert await counts(database) == (37, 119, 75)



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
    assert await counts(database) == (36, 118, 74)



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
    assert parse_qs(urlsplit(first.filter_examples["unregistered-scan"]).query) == {
        "library": [orphan.library], "archive_document": [str(orphan.document_id)],
    }
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
    third = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=second.cursor, return_total_count=True))
    fourth = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=third.cursor, return_total_count=True))
    fifth = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=fourth.cursor, return_total_count=True))
    sixth = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=fifth.cursor, return_total_count=True))
    seventh = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=sixth.cursor, return_total_count=True))
    eighth = await database.sources.document_library_filter_options(DocumentLibraryOptionsRequest(limit=1, cursor=seventh.cursor, return_total_count=True))
    assert first.total_count == 8 and eighth.cursor is None
    assert [batch.items[0].library for batch in (first, second, third, fourth, fifth, sixth, seventh, eighth)] == [
        'preview-counts', 'preview-mzk', 'preview-nlk', 'preview-pagination', 'preview-review-a', 'preview-review-b', 'preview-table', 'preview-table-mirror',
    ]
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
    key_actor = AuthContext(user_id=user.user_id, api_key_id=key.api_key_id, authentication_method='api_key', scopes=set())
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
        assert parse_qs(link.query).get('page_link_state', []) == selected
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

    scope = dict(entity_link_state=['manual', 'verified'],
                 library=['preview-mzk'], document_source_id=[result.documents['provenance-a']])
    # Faces: the same scope plus each face's own latest change.
    criteria = dict(scope, last_touched_by_user_id=[result.users['reviewer']],
                    last_touched_from=authority.last_touched_at,
                    last_touched_to=authority.last_touched_at)
    faces = await database.faces.list(FaceListRequest(filter_=FaceListFilter(entity_id=[person], **criteria), limit=1, return_total_count=True))
    assert [f.detection_id for f in faces.items] == [authority.detection_id]
    assert faces.total_count == 1 and faces.cursor is None
    # People/documents: the same scope through a linked annotation; their own
    # latest change, not the face's, satisfies the modification criteria.
    entities = await database.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(**scope), return_total_count=True))
    assert person in [e.entity_id for e in entities.items]
    own = dict(scope, last_touched_by_user_id=[identity.last_touched_by_user_id],
               last_touched_from=identity.last_touched_at, last_touched_to=identity.last_touched_at)
    entities = await database.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(**own)))
    assert [e.entity_id for e in entities.items] == [person]
    docs = await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(**scope), return_total_count=True))
    assert [d.source_id for d in docs.items] == [result.documents['provenance-a']]
    # Manual evidence is in the other document: unrelated witnesses cannot combine.
    impossible = {**scope, 'entity_link_state': ['manual']}
    assert person not in [e.entity_id for e in (await database.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(**impossible)))).items]
    assert not (await database.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(**impossible)))).items
    mentions = await database.text_mentions.list(TextMentionListRequest(limit=100, filter_=TextMentionListFilter(
        entity_id=[person], last_touched_by_user_id=[result.users['reviewer']]), return_total_count=True))
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
        detection_id=[detection_id], last_touched_from='2000-01-01T00:00:00Z')))
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
        filter_=EntityListFilter(library=['preview-mzk'], document_source_id=[seed.documents['provenance-a']])))
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
    reviewer_faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(source_id=[page_id], last_touched_by_user_id=[seed.users['reviewer']])))
    assert [item.detection_id for item in reviewer_faces.items] == [seed.faces['provenance-authority']]


@pytest.mark.asyncio
async def test_card_and_statistics_entry_points_resolve_attributed_evidence_and_media(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    hover = urlsplit(seed.filter_examples['scan-annotation-hover'])
    hover_page = await db.sources.get_page(seed.pages['provenance-a-1'])
    assert hover.path == (
        f'/libraries/{hover_page.library}/documents/{hover_page.document_id}'
        f'/pages/{hover_page.page_id}'
    )
    assert not hover.query  # Open every annotation, without hiding states.
    hover_faces = (await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(source_id=[hover_page.source_id]),
    ))).items
    assert {face.detection_id for face in hover_faces} == {
        seed.faces['provenance-auto'], seed.faces['provenance-authority'],
    }
    assert {face.entity_link_state.value for face in hover_faces} == {'automatic', 'verified'}
    hover_spans = await get_text_mention_spans(
        db, hover_page.source_id, library=hover_page.library,
        document_id=hover_page.document_id, page_id=hover_page.page_id,
    )
    assert hover_spans and all(span.entity_id == seed.entities['provenance-review'] for span in hover_spans)
    cards = urlsplit(seed.filter_examples['person-evidence-cards'])
    person_id = seed.entities['provenance-review']
    comparison = urlsplit(seed.filter_examples['person-face-style-comparison'])
    assert comparison.path == cards.path
    assert parse_qs(comparison.query) == {'tab': ['discover']}
    assert cards.path == f'/people/{person_id}'
    assert parse_qs(cards.query) == {
        'origin_matched_face': [str(seed.faces['provenance-authority'])],
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
    for state in ('automatic', 'manual', 'verified'):
        by_state = await db.faces.list(FaceListRequest(limit=100,
            filter_=FaceListFilter(entity_id=[person_id], entity_link_state=[state])))
        assert {face.detection_id for face in by_state.items} == {
            face.detection_id for face in filtered_faces if face.entity_link_state.value == state
        }
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
    assert query == {'q': ['Irena'], 'library': ['preview-mzk']}
    people = await db.entities.search(SearchEntitiesRequest(limit=100,
        query=QueryBase(text=query['q']),
        filter_=EntityListFilter(library=query['library']),
    ))
    assert [person.entity_id for person in people.items] == [seed.entities['provenance-review']]
    # The profile applies the same library scope to her faces.
    faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        entity_id=[people.items[0].entity_id], library=query['library'],
    )))
    assert {face.detection_id for face in faces.items} == {
        seed.faces['provenance-auto'], seed.faces['provenance-authority'],
    }
    changed = await db.entities.search(SearchEntitiesRequest(limit=100,
        query=QueryBase(text=query['q']),
        filter_=EntityListFilter(library=['preview-absent']),
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
    # Canonical document scope: the internal registered document UUID.
    assert query == {'document': [str(seed.documents['provenance-a'])]}
    pages = await db.sources.list_pages(PageListRequest(limit=100, filter_=PageListFilter(
        document_source_id=query['document'],
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
    assert (await db.entities.get(before_person.entity_id)).model_dump(exclude={'thumbnail_face_id', 'thumbnail_mode'}) == before_person.model_dump(exclude={'thumbnail_face_id', 'thumbnail_mode'})
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        assert await db.faces.get(before_face.detection_id) == before_face
        assert (await db.entities.get(before_person.entity_id)).model_dump(exclude={'thumbnail_face_id', 'thumbnail_mode'}) == before_person.model_dump(exclude={'thumbnail_face_id', 'thumbnail_mode'})


@pytest.mark.asyncio
async def test_annotation_editor_example_uses_same_user_and_key_and_preserves_creation(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    example = urlsplit(seed.filter_examples['annotation-editor-filters'])
    query = parse_qs(example.query)
    assert example.path == f"/people/{seed.entities['provenance-review']}"
    assert query == {
        'touched_by': [str(seed.users['importer'])],
        'api_key': [str(seed.api_keys['importer'])],
    }
    matches = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        entity_id=[seed.entities['provenance-review']],
        last_touched_by_user_id=query['touched_by'],
        last_touched_by_api_key_id=query['api_key'],
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
    # A page's own latest change: the importer's faces, before OCR/review edits.
    filtered = await db.sources.list_pages(PageListRequest(limit=100,
        return_total_count=True, filter_=PageListFilter(**scope,
            last_touched_by_user_id=[seed.users['importer']])))
    assert filtered.total_count == 3
    assert untouched.source_id not in {page.source_id for page in filtered.items}
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        assert await db.sources.get_page(untouched.source_id) == untouched


async def _page_mention_lines(database, page):
    """Map each identity to the OCR lines its linked mention spans cover on a page."""
    spans = await get_text_mention_spans(
        database, page.source_id, library=page.library,
        document_id=page.document_id, page_id=page.page_id,
    )
    layout = await get_page_layout(page.library, page.document_id, page.page_id)
    order = [line.id for region in layout.regions for line in region.lines]
    by_entity: dict[uuid.UUID, set[str]] = {}
    by_mention: dict[uuid.UUID, set[str]] = {}
    for span in spans:
        # A span covers its start line, its end line and every line between.
        covered = order[order.index(span.start_line_id):order.index(span.end_line_id) + 1]
        assert covered, "span lines must resolve in the stored layout"
        by_entity.setdefault(span.entity_id, set()).update(covered)
        by_mention.setdefault(span.mention_id, set()).update(covered)
    return by_entity, by_mention


@pytest.mark.asyncio
async def test_person_mention_highlights_follow_linked_identity_and_preserve_review(seed_target):
    database, filesystem, _ = seed_target
    result = await preview.seed_preview(database, filesystem)
    page = await database.sources.get_page(result.pages["focus-1"])
    example = urlsplit(result.filter_examples["person-mention-highlights"])
    assert example.path == (
        f"/libraries/{page.library}/documents/{page.document_id}/pages/{page.page_id}"
    )
    assert result.filter_examples["viewport-focus"] == example.path
    assert parse_qs(example.query) == {"selectedPerson": [str(result.entities["ada"])]}

    ada, lenka = result.entities["ada"], result.entities["lenka"]
    upper, lower = result.mentions["focus-name-upper"], result.mentions["focus-name-lower"]
    by_entity, by_mention = await _page_mention_lines(database, page)
    # Every line of each of Ada's linked mention records is an Ada line.
    assert {"focus-name-upper", "focus-name-lower"} <= by_mention[upper] | by_mention[lower]
    assert by_entity[ada] == by_mention[upper] | by_mention[lower]
    assert lenka not in by_entity

    reviewed = await database.text_mentions.patch(
        lower,
        TextMentionPatchRequest(entity_id=lenka),
        GenericActor(user_id=result.users["reviewer"]),
    )
    reviewed_person = await database.entities.get(lenka)
    assert await preview.seed_preview(database, filesystem) == result
    by_entity, by_mention = await _page_mention_lines(database, page)
    # Highlights follow the linked identity of each record, not the line text:
    # Ada keeps exactly her remaining record's lines and Lenka gains the
    # reviewed record's lines. Both records name "Ada Novak", so the name-based
    # span resolution places each of them on both occurrences.
    assert by_entity[ada] == by_mention[upper]
    assert by_entity[lenka] == by_mention[lower]
    assert "focus-name-lower" in by_entity[lenka]
    assert await database.text_mentions.get(reviewed.mention_id) == reviewed
    assert await database.entities.get(lenka) == reviewed_person


@pytest.mark.asyncio
async def test_person_mention_highlights_cover_multi_line_mentions_by_identity(seed_target):
    database, filesystem, _ = seed_target
    result = await preview.seed_preview(database, filesystem)
    page = await database.sources.get_page(result.pages["links-2"])
    example = urlsplit(result.filter_examples["person-mention-highlights-multiline"])
    assert example.path == (
        f"/libraries/{page.library}/documents/{page.document_id}/pages/{page.page_id}"
    )
    link_ada, link_emil = result.entities["link-ada"], result.entities["link-emil"]
    assert parse_qs(example.query) == {"selectedPerson": [str(link_ada)]}

    by_entity, _ = await _page_mention_lines(database, page)
    # Ada Review's verified mention spans both fragments of one OCR mention;
    # Emil Review's unlinked line carries no identity.
    assert by_entity == {
        link_ada: {"links-verified-mention-0", "links-verified-mention-1"},
    }
    assert link_emil not in by_entity

    # A reviewer links the "Emil Review" line to Ada Review: the line is now
    # Ada Review's by identity although its text never names her.
    unlinked = result.mentions["links-unassigned-mention"]
    reviewed = await database.text_mentions.patch(
        unlinked,
        TextMentionPatchRequest(entity_id=link_ada),
        GenericActor(user_id=result.users["reviewer"]),
    )
    assert await preview.seed_preview(database, filesystem) == result
    by_entity, by_mention = await _page_mention_lines(database, page)
    assert by_mention[unlinked] == {"links-unassigned-mention"}
    assert by_entity[link_ada] == {
        "links-verified-mention-0", "links-verified-mention-1", "links-unassigned-mention",
    }
    assert await database.text_mentions.get(unlinked) == reviewed


@pytest.mark.asyncio
async def test_viewport_focus_targets_and_repeated_occurrences(seed_target):
    database, filesystem, _ = seed_target
    result = await preview.seed_preview(database, filesystem)
    page = await database.sources.get_page(result.pages["focus-1"])
    layout = await get_page_layout(page.library, page.document_id, page.page_id)
    spans = await get_text_mention_spans(database, page.source_id, library=page.library,
                                       document_id=page.document_id, page_id=page.page_id)
    assert {span.mention_id for span in spans} == {
        result.mentions["focus-name-upper"], result.mentions["focus-name-lower"]
    }
    assert {span.entity_id for span in spans} == {result.entities["ada"]}
    assert len({span.start_line_id for span in spans}) == 2
    lines = {line.id: line for region in layout.regions for line in region.lines}
    assert {lines[span.start_line_id].polygon[0][1] for span in spans} == {460, 1000}
    upper = await database.faces.get(result.faces["focus-upper"])
    lower = await database.faces.get(result.faces["focus-lower"])
    tiny = await database.faces.get(result.faces["focus-tiny"])
    assert lower.bounding_box.y > upper.bounding_box.y + upper.bounding_box.height
    assert tiny.bounding_box.width == 16 and tiny.bounding_box.height == 19
    for face in (upper, lower, tiny):
        box = face.bounding_box
        assert all(box.x <= point.x <= box.x + box.width and
                   box.y <= point.y <= box.y + box.height for point in face.keypoints)
    assert urlsplit(result.filter_examples["viewport-focus"]).path.endswith(f"/pages/{page.page_id}")
    reviewed = await database.faces.patch(
        lower.detection_id, FacePatchRequest(entity_id=result.entities["lenka"]),
        GenericActor(user_id=result.users["reviewer"]),
    )
    reviewed_person = await database.entities.get(result.entities["lenka"])
    repeated = await preview.seed_preview(database, filesystem)
    assert repeated.faces == result.faces and repeated.mentions == result.mentions
    stored = await database.faces.get(lower.detection_id)
    assert stored.entity_id == result.entities["lenka"]
    assert stored == reviewed
    assert (await database.entities.get(result.entities["lenka"])).last_touched_at == reviewed_person.last_touched_at


@pytest.mark.asyncio
async def test_person_last_change_example_shows_mixed_annotation_states(seed_target):
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    example = urlsplit(seed.filter_examples['person-last-change'])
    assert example.path == f"/people/{seed.entities['link-ada']}"
    person = await db.entities.get(seed.entities['link-ada'])
    stats = person.entity_link_stats
    for counts in (stats.faces, stats.mentions):
        assert counts.automatic == 1 and counts.manual == 0 and counts.verified == 1
        assert counts.total == 2
    assert person.last_touched_at is not None
    editor = await db.users.get(person.last_touched_by_user_id)
    assert editor.display_name
    for _ in range(2):
        rerun = await preview.seed_preview(db, filesystem)
        assert rerun.filter_examples['person-last-change'] == seed.filter_examples['person-last-change']
        assert await db.entities.get(seed.entities['link-ada']) == person


async def _all_document_pages(database, library, document_id, batch_size):
    pages, cursor = [], None
    while True:
        result = await database.sources.list_pages(PageListRequest(
            limit=batch_size, cursor=cursor, return_total_count=True,
            filter_=PageListFilter(library=[library], document_id=[document_id]),
        ))
        pages.append(result)
        cursor = result.cursor
        if cursor is None:
            return pages


@pytest.mark.asyncio
async def test_page_gallery_lists_every_registered_page_in_stable_batches(seed_target):
    database, filesystem, _ = seed_target
    seed = await preview.seed_preview(database, filesystem)
    spec = next(item for item in DOCUMENTS if item.key == "page-gallery")
    expected = {seed.pages[f"page-gallery-{i}"] for i in range(1, PAGE_GALLERY_PAGES + 1)}
    # The frontend requests 12 pages per batch; the fixture needs a second one.
    batches = await _all_document_pages(database, spec.library, spec.document_id, 12)
    assert [len(batch.items) for batch in batches] == [12, PAGE_GALLERY_PAGES - 12]
    assert {batch.total_count for batch in batches} == {PAGE_GALLERY_PAGES}
    ordered = [item.source_id for batch in batches for item in batch.items]
    assert len(ordered) == len(set(ordered)) and set(ordered) == expected
    assert all(item.library == spec.library and item.document_id == spec.document_id
               for batch in batches for item in batch.items)
    # The documented order is the stable source-key order, repeated across reads.
    assert ordered == sorted(ordered)
    smaller = await _all_document_pages(database, spec.library, spec.document_id, 5)
    assert [item.source_id for batch in smaller for item in batch.items] == ordered

    # Every page with media has a usable gallery thumbnail; the missing-media
    # page stays registered and navigable while its image resolves to 404.
    for i in range(1, PAGE_GALLERY_PAGES + 1):
        page = await database.sources.get_page(seed.pages[f"page-gallery-{i}"])
        if i == PAGE_GALLERY_MISSING_MEDIA:
            with pytest.raises(SourceResolutionError) as missing:
                await get_page_image(page.library, page.document_id, page.page_id, max_width=256)
            assert missing.value.status_code == 404
            continue
        thumbnail = await get_page_image(page.library, page.document_id, page.page_id, max_width=256)
        with Image.open(io.BytesIO(thumbnail.content)) as image:
            assert image.width <= 256

    link = urlsplit(seed.filter_examples["document-page-gallery"])
    target = next(item.page_id for item in PAGES if item.key == "page-gallery-13")
    assert link.path == f"/libraries/{spec.library}/documents/{spec.document_id}/pages/{target}"
    assert await database.sources.lookup_page(PageLookupRequest(
        library=spec.library, document_id=spec.document_id, page_id=target,
    )) is not None

    # Annotation filters narrow evidence on the scan, never its gallery.
    filtered = urlsplit(seed.filter_examples["document-page-gallery-filtered"])
    search = next(item for item in DOCUMENTS if item.key == "issue8-search")
    assert filtered.path.startswith(f"/libraries/{search.library}/documents/{search.document_id}/pages/")
    importer = parse_qs(filtered.query)["touched_by"]
    assert importer == [str(seed.users["importer"])]
    narrowed = await database.sources.list_pages(PageListRequest(
        limit=100, return_total_count=True,
        filter_=PageListFilter(library=[search.library], document_id=[search.document_id],
                               last_touched_by_user_id=[seed.users["importer"]]),
    ))
    unfiltered = await _all_document_pages(database, search.library, search.document_id, 12)
    assert narrowed.total_count == 3 and unfiltered[0].total_count == 6

    for _ in range(2):
        assert await preview.seed_preview(database, filesystem) == seed
        again = await _all_document_pages(database, spec.library, spec.document_id, 12)
        assert [item.source_id for batch in again for item in batch.items] == ordered


@pytest.mark.asyncio
async def test_canonical_portraits_media_and_review_preservation(seed_target):
    database, filesystem, _ = seed_target
    first = await preview.seed_preview(database, filesystem)
    manual = await database.entities.get(first.entities['provenance-review'])
    from people_gator_api.schemas.faces import FaceListFilter
    linked = (await database.faces.list(FaceListRequest(limit=100,
        filter_=FaceListFilter(entity_id=[manual.entity_id])))).items
    assert manual.thumbnail_mode == 'manual'
    assert urlsplit(first.filter_examples['person-portrait-selection']).path == f'/people/{manual.entity_id}'
    assert manual.thumbnail_face_id == linked[-1].detection_id
    assert manual.thumbnail_face_id != linked[0].detection_id
    selected_face = await database.faces.get(manual.thumbnail_face_id)
    source = await database.sources.lookup(GenericSourceLookupRequest(source_id=selected_face.source_id))
    crop = await get_aligned_face_crop(first.users['reviewer'], selected_face, source, max_width=256)
    assert crop.content
    automatic = await database.entities.get(first.entities['ada'])
    assert automatic.thumbnail_mode == 'automatic' and automatic.thumbnail_face_id
    # A later assignment and an identity edit preserve the saved automatic face.
    actor = GenericActor(user_id=first.users['reviewer'])
    new_face = FaceCreateRequest(source_id=selected_face.source_id,
        entity_id=automatic.entity_id, confidence=selected_face.confidence,
        bounding_box=selected_face.bounding_box, keypoints=selected_face.keypoints)
    await database.faces.create(new_face, actor)
    edited = await database.entities.patch(automatic.entity_id,
        EntityPatchRequest(description="Reviewed automatic portrait"), actor)
    assert edited.thumbnail_face_id == automatic.thumbnail_face_id
    assert edited.thumbnail_mode == 'automatic'
    await preview.seed_preview(database, filesystem)
    assert await database.entities.get(automatic.entity_id) == edited
    empty = await database.entities.get(first.entities['nora'])
    assert empty.thumbnail_mode == 'automatic' and empty.thumbnail_face_id is None
    # An explicit reset is a review choice and must survive reseeding unchanged.
    actor = GenericActor(user_id=first.users['reviewer'])
    reset = await database.entities.patch(manual.entity_id, EntityPatchRequest(thumbnail_face_id=None), actor)
    assert await preview.seed_preview(database, filesystem) == first
    assert await database.entities.get(manual.entity_id) == reset
    selected = await database.entities.patch(manual.entity_id, EntityPatchRequest(thumbnail_face_id=linked[0].detection_id), actor)
    await preview.seed_preview(database, filesystem)
    assert await database.entities.get(manual.entity_id) == selected


@pytest.mark.asyncio
@pytest.mark.parametrize('intervening_review', [False, True])
async def test_portrait_upgrade_checkpoint_recovery_preserves_review(seed_target, monkeypatch, intervening_review):
    database, filesystem, _ = seed_target
    original = filesystem.write_bytes
    failed = False
    async def interrupt(key, content):
        nonlocal failed
        if key == preview.UPGRADES_KEY:
            upgrade = preview.SeedUpgrades.model_validate_json(content).thumbnail.get('person-portrait-v1')
            if upgrade is not None and upgrade.complete and not failed:
                failed = True
                raise OSError('portrait checkpoint interrupted')
        await original(key, content)
    monkeypatch.setattr(filesystem, 'write_bytes', interrupt)
    with pytest.raises(OSError, match='portrait checkpoint'):
        await preview.seed_preview(database, filesystem)
    saved = preview.SeedManifest.model_validate_json(await filesystem.read_bytes(preview.MANIFEST_KEY))
    person_id = saved.entities['provenance-review']
    person = await database.entities.get(person_id)
    assert person.thumbnail_mode == 'manual'
    if intervening_review:
        person = await database.entities.patch(person_id, EntityPatchRequest(thumbnail_face_id=None),
            GenericActor(user_id=person.user_id))
    await preview.seed_preview(database, filesystem)
    assert await database.entities.get(person_id) == person
    # Rolled-back seed code rejects unknown identity-manifest keys.
    identity = json.loads(await filesystem.read_bytes(preview.MANIFEST_KEY))
    assert set(identity) == {'entities', 'faces', 'mentions'}


@pytest.mark.asyncio
async def test_legacy_portrait_upgrade_state_moves_out_of_identity_manifest(seed_target, tmp_path):
    database, filesystem, _ = seed_target
    await preview.seed_preview(database, filesystem)
    # Early #35 previews kept upgrade state inside the identity manifest.
    identity = json.loads(await filesystem.read_bytes(preview.MANIFEST_KEY))
    upgrades = json.loads(await filesystem.read_bytes(preview.UPGRADES_KEY))
    identity['thumbnail_upgrades'] = upgrades['thumbnail']
    await filesystem.write_bytes(preview.MANIFEST_KEY, json.dumps(identity).encode())
    (tmp_path / preview.UPGRADES_KEY).unlink()
    person_id = uuid.UUID(identity['entities']['provenance-review'])
    reset = await database.entities.patch(person_id, EntityPatchRequest(thumbnail_face_id=None),
        GenericActor(user_id=(await database.entities.get(person_id)).user_id))
    await preview.seed_preview(database, filesystem)
    # The completed upgrade is not repeated over the later reviewer reset.
    assert await database.entities.get(person_id) == reset
    assert set(json.loads(await filesystem.read_bytes(preview.MANIFEST_KEY))) == {'entities', 'faces', 'mentions'}
    moved = preview.SeedUpgrades.model_validate_json(await filesystem.read_bytes(preview.UPGRADES_KEY))
    assert moved.thumbnail['person-portrait-v1'].complete


@pytest.mark.asyncio
async def test_sorting_scenario_orders_groups_and_survives_reruns(seed_target):
    """Issue #33: the preview demonstrates sorting through repositories, not counts."""
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionGroupListRequest, TextMentionListFilter
    from people_gator_api.schemas.sources import DocumentListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    person = seed.entities["sorting"]
    for key in ("sorting-documents", "sorting-people", "sorting-scans", "sorting-faces",
                "sorting-mention-groups", "sorting-similar-faces", "sorting-document-names"):
        assert key in seed.filter_examples
    assert parse_qs(urlsplit(seed.filter_examples["sorting-mention-groups"]).query) == {
        "tab": ["mentions"], "mention_view": ["groups"], "group_sort": ["count"]}

    # Faces sort by confidence across pages; unassigned similar evidence stays separate.
    faces = await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(entity_id=[person]), sort="confidence", sort_direction="desc"))
    assert [face.confidence for face in faces.items] == [0.88, 0.75, 0.62]
    states = await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(entity_id=[person]), sort="link_state"))
    assert [face.entity_link_state.value for face in states.items] == ["verified", "manual", "automatic"]

    # Exact recorded text stays distinct; counts cover every matching occurrence.
    groups = await db.text_mentions.list_groups(TextMentionGroupListRequest(
        limit=10, return_total_count=True, filter_=TextMentionListFilter(entity_id=[person]),
        sort="count"))
    assert [(group.name, group.occurrence_count) for group in groups.items] == [
        ("Marta Řádková", 3), ("M. Řádková", 1), ("MARTA ŘÁDKOVÁ", 1), ("Marta Radkova", 1)]
    occurrences = await db.text_mentions.list(TextMentionListRequest(
        limit=1, return_total_count=True, sort="source",
        filter_=TextMentionListFilter(entity_id=[person], name=["Marta Řádková"])))
    assert occurrences.total_count == 3 and occurrences.cursor

    # Accent/case name variants sort adjacently; uneven page counts tie-break by ID.
    documents = await db.sources.list_documents(DocumentListRequest(
        limit=10, sort="name", filter_=DocumentListFilter(document_id=[
            next(item.document_id for item in DOCUMENTS if item.key == key)
            for key in ("sorting-ledger", "sorting-notes")])))
    # "Ř" folds to "r", so the accented ledger precedes "notes" instead of following "z".
    assert [item.name for item in documents.items] == ["Řádková ledger", "radkova notes"]
    pages = await db.sources.list_documents(DocumentListRequest(
        limit=100, sort="page_count", filter_=DocumentListFilter(library=["preview-nlk"])))
    assert pages.items[0].document_id == next(
        item.document_id for item in DOCUMENTS if item.key == "sorting-ledger")

    # Similar-face discovery sorts its bounded candidate set, not only a loaded page.
    similar = await db.faces.search(SearchFacesRequest(
        limit=100, query=QueryBase(face_id=[seed.faces["sorting-manual"]], face_embedding_model=MODEL),
        sort="confidence", sort_direction="desc"))
    confidences = [face.confidence for face in similar.items]
    assert confidences == sorted(confidences, reverse=True)
    assert seed.faces["sorting-similar"] in {face.detection_id for face in similar.items}

    # Reviewer edits and checkpointed identities survive a rerun.
    reviewed = await db.faces.patch(seed.faces["sorting-automatic"],
                                    FacePatchRequest(entity_id=None), GenericActor(user_id=seed.users["reviewer"]))
    again = await preview.seed_preview(db, filesystem)
    assert again.faces == seed.faces and again.mentions == seed.mentions
    stored = await db.faces.get(seed.faces["sorting-automatic"])
    assert stored.entity_id is None and stored.last_touched_at == reviewed.last_touched_at


@pytest.mark.asyncio
async def test_default_documents_landing_has_linked_media_and_preserves_reviews(seed_target):
    database, filesystem, _ = seed_target
    seed = await preview.seed_preview(database, filesystem)
    assert seed.filter_examples["default-documents"] == "/"

    async def landing_documents():
        # Match the unfiltered landing list, including its 12-document batches.
        documents, cursor = [], None
        while True:
            batch = await database.sources.list_documents(DocumentListRequest(
                limit=12, cursor=cursor, return_total_count=True,
            ))
            documents.extend(batch.items)
            cursor = batch.cursor
            if cursor is None:
                assert len(documents) == batch.total_count
                return documents

    documents = await landing_documents()
    assert len({item.source_id for item in documents}) == len(documents)
    assert {item.source_id for item in documents} == set(seed.documents.values())
    album = next(item for item in documents if item.source_id == seed.documents["album"])
    assert album.name == "Portrait album"
    scans = urlsplit(seed.filter_examples["default-documents-scans"])
    assert scans.path == "/scans"
    assert parse_qs(scans.query) == {"document": [str(album.source_id)]}
    pages = await database.sources.list_pages(PageListRequest(
        limit=4, return_total_count=True,
        filter_=PageListFilter(document_source_id=[album.source_id]),
    ))
    assert {page.source_id for page in pages.items} == {
        seed.pages["album-1"], seed.pages["album-2"],
    }
    assert pages.total_count == 2
    thumbnails = {}
    for page in pages.items:
        assert await database.sources.lookup_page(PageLookupRequest(
            library=album.library, document_id=album.document_id, page_id=page.page_id,
        )) == page
        thumbnail = await get_page_image(
            page.library, page.document_id, page.page_id, max_width=256,
        )
        with Image.open(io.BytesIO(thumbnail.content)) as image:
            assert image.width == 256 and image.height > 0
        thumbnails[page.source_id] = thumbnail.content

    reviewed = await database.faces.patch(
        seed.faces["unassigned-ada"],
        FacePatchRequest(entity_id=seed.entities["lenka"]),
        GenericActor(user_id=seed.users["reviewer"]),
    )
    before_documents = await landing_documents()
    before_pages = [await database.sources.get_page(page.source_id) for page in pages.items]
    manifest = await filesystem.read_bytes(preview.MANIFEST_KEY)
    repeated = await preview.seed_preview(database, filesystem)
    assert repeated == seed
    assert await landing_documents() == before_documents
    assert await database.faces.get(reviewed.detection_id) == reviewed
    assert await filesystem.read_bytes(preview.MANIFEST_KEY) == manifest
    for page in before_pages:
        assert await database.sources.get_page(page.source_id) == page
        thumbnail = await get_page_image(
            page.library, page.document_id, page.page_id, max_width=256,
        )
        assert thumbnail.content == thumbnails[page.source_id]


@pytest.mark.asyncio
async def test_entity_discovery_choices_many_faces_and_degenerate_vectors(seed_target):
    import math
    from people_gator_api.schemas.search import EntitySearchQuery
    from people_gator_api.seeding.fixtures import DISCOVERY_MODEL, DISCOVERY_OTHER_MODEL

    db, filesystem, _ = seed_target
    first = await preview.seed_preview(db, filesystem)
    reference = first.entities["discovery"]
    for annotation, expected in (("faces", "discovery-face"), ("name", "discovery-name"), ("aliases", "discovery-alias")):
        query = EntitySearchQuery(entity_id=reference, entity_annotations=[annotation], face_embedding_model=DISCOVERY_MODEL)
        people = await db.entities.search(SearchEntitiesRequest(limit=20, query=query))
        assert people.items[0].entity_id == first.entities[expected]
        faces = await db.faces.search(SearchFacesRequest(limit=40, query=query))
        assert first.faces[{"faces": "discovery-face-match", "name": "discovery-name-match", "aliases": "discovery-alias-match"}[annotation]] in {face.detection_id for face in faces.items}
        for hit in [*people.items, *faces.items]:
            assert math.isfinite(hit.score)
            assert hit.face_score is None or math.isfinite(hit.face_score)
        if annotation == "faces":
            assert first.faces["discovery-zero-candidate"] not in {face.detection_id for face in faces.items}
            assert first.faces["discovery-zero-candidate"] not in people.items[0].matched_detection_ids
    references = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(entity_id=[reference])))
    assert len(references.items) == 15
    assert (await db.faces.get(first.faces['discovery-missing'])).embeddings == []
    assert (await db.faces.get(first.faces['discovery-other-model'])).embeddings == [DISCOVERY_OTHER_MODEL]
    identifier_example = parse_qs(urlsplit(first.filter_examples['entity-discovery-identifier']).query)
    assert identifier_example['discovery_annotations'] == ['none']
    identifier_results = await db.faces.search(SearchFacesRequest(
        limit=40, query=QueryBase(text=identifier_example['discovery_text']),
    ))
    assert identifier_results.items[0].detection_id == first.faces['discovery-unassigned']
    assert identifier_results.items[0].face_score is None
    assert identifier_results.items[0].text_score == 1
    # Retain operator-reviewed inputs and assignments on an additive rerun.
    actor = GenericActor(user_id=first.users["reviewer"])
    edited = await db.entities.patch(reference, EntityPatchRequest(aliases=["Reviewed navigator"]), actor)
    assigned = await db.faces.patch(first.faces['discovery-unassigned'], FacePatchRequest(entity_id=reference), actor)
    before = await db.entities.get(reference)
    second = await preview.seed_preview(db, filesystem)
    assert second == first
    retained = await db.entities.get(reference)
    assert retained.aliases == edited.aliases
    assert retained.last_touched_at == before.last_touched_at
    assert (await db.faces.get(assigned.detection_id)).entity_id == reference
    assert parse_qs(urlsplit(first.filter_examples['entity-discovery']).query)['discovery_model'] == [DISCOVERY_MODEL]
    page = await db.sources.get_page(first.pages['discovery-8'])
    crop = await get_aligned_face_crop(actor.user_id, await db.faces.get(first.faces['discovery-face-match']), page, max_width=128)
    with Image.open(io.BytesIO(crop.content)) as image:
        assert image.size == (128, 128)


@pytest.mark.asyncio
async def test_shared_filter_scenario_transfers_own_latest_changes(seed_target):
    """#52: one curator selection finds each view's own latest change."""
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.sources import DocumentListFilter

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    curator = seed.users["curator"]
    key = seed.api_keys["curator"]
    ivo, hana = seed.entities["shared-ivo"], seed.entities["shared-hana"]
    ledger, mirror = seed.documents["shared-ledger"], seed.documents["shared-mirror"]

    def query(name):
        return parse_qs(urlsplit(seed.filter_examples[name]).query)

    assert query("shared-filters-documents") == {"touched_by": [str(curator)]}
    assert query("shared-filters-people") == {"touched_by": [str(curator)]}
    documents = await db.sources.list_documents(DocumentListRequest(limit=100, filter_=DocumentListFilter(
        last_touched_by_user_id=[curator])))
    assert [item.source_id for item in documents.items] == [ledger]
    people = await db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        last_touched_by_user_id=[curator])))
    assert {item.entity_id for item in people.items} == {ivo, hana}
    # Hana's own record was the curator's; her linked face remains the reviewer's.
    hana_record = await db.entities.get(hana)
    face = await db.faces.get(seed.faces["shared-hana-face"])
    assert hana_record.last_touched_by_user_id == curator and hana_record.last_touched_by_api_key_id is None
    assert face.last_touched_by_user_id == seed.users["reviewer"]
    assert query("shared-filters-api-key") == {"touched_by": [str(curator)], "api_key": [str(key)]}
    keyed = await db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        last_touched_by_user_id=[curator], last_touched_by_api_key_id=[key])))
    assert [item.entity_id for item in keyed.items] == [ivo]
    profile = urlsplit(seed.filter_examples["shared-filters-person-faces"])
    assert profile.path == f"/people/{hana}"
    faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        entity_id=[hana], last_touched_by_user_id=[curator])))
    assert not faces.items
    # Document scope uses the internal UUID; the same archive ID elsewhere has no links.
    assert query("shared-filters-scope") == {"document": [str(ledger)]}
    scoped = await db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        document_source_id=[ledger])))
    assert {item.entity_id for item in scoped.items} == {ivo, hana}
    assert not (await db.entities.list(EntityListRequest(limit=100, filter_=EntityListFilter(
        document_source_id=[mirror])))).items
    pages = await db.sources.list_pages(PageListRequest(limit=100, filter_=PageListFilter(
        library=["preview-nlk"], document_source_id=[mirror])))
    assert [item.source_id for item in pages.items] == [seed.pages["shared-mirror-1"]]

    # Reruns keep the edit once; a later review edit is never overwritten.
    edited = await db.entities.patch(hana, EntityPatchRequest(short_description="Reviewed"),
                                     GenericActor(user_id=seed.users["reviewer"]))
    for _ in range(2):
        assert await preview.seed_preview(db, filesystem) == seed
        assert await db.entities.get(hana) == edited
        assert await db.faces.get(face.detection_id) == face


@pytest.mark.asyncio
async def test_shared_page_scope_matches_pages_without_parent_documents(seed_target):
    from people_gator_api.schemas.faces import FaceListFilter
    from people_gator_api.schemas.mentions import TextMentionListFilter
    from people_gator_api.schemas.sources import (
        DocumentListFilter, GenericSourceListFilter, GenericSourceListRequest,
    )

    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    selected = seed.pages["shared-ledger-1"]
    for key, path in (("shared-filters-page", "/scans"), ("shared-filters-page-people", "/people")):
        example = urlsplit(seed.filter_examples[key])
        assert example.path == path
        assert parse_qs(example.query) == {"page": [str(selected)]}

    sources = await db.sources.list(GenericSourceListRequest(
        limit=100, return_total_count=True,
        filter_=GenericSourceListFilter(page_source_id=[selected]),
    ))
    assert [item.source_id for item in sources.items] == [selected]
    assert sources.total_count == 1
    documents = await db.sources.list_documents(DocumentListRequest(
        limit=100, filter_=DocumentListFilter(page_source_id=[selected]),
    ))
    assert not documents.items
    people = await db.entities.list(EntityListRequest(
        limit=100, filter_=EntityListFilter(page_source_id=[selected]),
    ))
    assert [item.entity_id for item in people.items] == [seed.entities["shared-hana"]]
    faces = await db.faces.list(FaceListRequest(
        limit=100, filter_=FaceListFilter(page_source_id=[selected]),
    ))
    assert [item.detection_id for item in faces.items] == [seed.faces["shared-hana-face"]]

    # These existing non-page fixtures have actual annotations. A page filter
    # must not mistake their UUIDs for pages, even alongside a valid selection.
    image_face = await db.faces.get(seed.faces["issue8-image-face"])
    invalid_ids = [seed.documents["issue8-direct"], image_face.source_id]
    for source_id in invalid_ids:
        assert not (await db.entities.list(EntityListRequest(
            limit=100, filter_=EntityListFilter(page_source_id=[source_id]),
        ))).items
        assert not (await db.text_mentions.list(TextMentionListRequest(
            limit=100, filter_=TextMentionListFilter(page_source_id=[source_id]),
        ))).items
        assert not (await db.faces.list(FaceListRequest(
            limit=100, filter_=FaceListFilter(page_source_id=[source_id]),
        ))).items
    sources = await db.sources.list(GenericSourceListRequest(
        limit=100, filter_=GenericSourceListFilter(page_source_id=[selected, *invalid_ids]),
    ))
    assert [item.source_id for item in sources.items] == [selected]

    # New report links are additive and a second seed keeps the reviewed graph.
    face = await db.faces.get(seed.faces["shared-hana-face"])
    assert await preview.seed_preview(db, filesystem) == seed
    assert await db.faces.get(face.detection_id) == face


@pytest.mark.asyncio
async def test_shared_filter_edit_recovers_from_interrupted_checkpoint(seed_target, monkeypatch):
    """An edit written before its completion checkpoint is not repeated."""
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    hana = seed.entities["shared-hana"]
    applied = await db.entities.get(hana)
    upgrades = preview.SeedUpgrades.model_validate_json(await filesystem.read_bytes(preview.UPGRADES_KEY))
    upgrades.record_edits["shared-filters-own-edit-v1"].complete = False
    await filesystem.write_bytes(preview.UPGRADES_KEY, upgrades.model_dump_json().encode())
    patches = []
    original = db.entities.patch

    async def recording_patch(*args, **kwargs):
        patches.append(args[0])
        return await original(*args, **kwargs)

    monkeypatch.setattr(db.entities, "patch", recording_patch)
    assert await preview.seed_preview(db, filesystem) == seed
    assert hana not in patches
    assert await db.entities.get(hana) == applied
    upgrades = preview.SeedUpgrades.model_validate_json(await filesystem.read_bytes(preview.UPGRADES_KEY))
    assert upgrades.record_edits["shared-filters-own-edit-v1"].complete


@pytest.mark.asyncio
async def test_list_pagination_scenario_crosses_browse_and_search_batches(seed_target, monkeypatch):
    from people_gator_api.schemas.search import SearchDocumentsRequest, SearchPagesRequest
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.seeding.fixtures import PAGINATION_ITEMS

    database, filesystem, _ = seed_target
    # Upgrade a retained pre-pagination preview, preserving its reviewed records.
    with monkeypatch.context() as legacy:
        for name in ("PEOPLE", "DOCUMENTS", "PAGES"):
            legacy.setattr(preview, name, tuple(
                item for item in getattr(preview, name)
                if not item.key.startswith("pagination-")
            ))
        old = await preview.seed_preview(database, filesystem)
    actor = GenericActor(user_id=old.users["reviewer"])
    reviewed = await database.entities.patch(
        old.entities["ada"], EntityPatchRequest(name="Reviewed Ada"), actor,
    )
    first = await preview.seed_preview(database, filesystem)
    for name in ("entities", "documents", "pages", "faces", "mentions"):
        assert getattr(old, name).items() <= getattr(first, name).items()
    assert (await database.entities.get(reviewed.entity_id)).last_touched_at == reviewed.last_touched_at
    keys = [f"pagination-{i}" for i in range(1, PAGINATION_ITEMS + 1)]
    people = {first.entities[key] for key in keys}
    documents = {first.documents[key] for key in keys}
    pages = {first.pages[key] for key in keys}
    library = ["preview-pagination"]
    browse_filters = {}
    for screen in ("people", "scans"):
        link = urlsplit(first.filter_examples[f"pagination-browse-{screen}"])
        assert link.path == f"/{screen}"
        params = parse_qs(link.query)
        assert "q" not in params
        browse_filters[screen] = params["library"]

    async def check_batches(fetch, request, expected, id_field):
        initial = await fetch(request)
        assert len(initial.items) == 12 and initial.cursor is not None
        final = await fetch(request.model_copy(update={"cursor": initial.cursor}))
        assert len(final.items) == PAGINATION_ITEMS - 12 and final.cursor is None
        ids = [getattr(item, id_field) for item in [*initial.items, *final.items]]
        assert len(ids) == len(set(ids)) and set(ids) == expected
        assert initial.total_count == PAGINATION_ITEMS
        # Replaying the initial cursor preserves server order.
        assert [getattr(item, id_field) for item in (await fetch(request)).items] == ids[:12]

    for searching in (False, True):
        common = dict(limit=12, return_total_count=True)
        query = QueryBase(text=["Pagination"])
        await check_batches(
            database.entities.search if searching else database.entities.list,
            SearchEntitiesRequest(**common, query=query, filter_=EntityListFilter(library=library))
            if searching else EntityListRequest(**common, filter_=EntityListFilter(library=browse_filters["people"])),
            people, "entity_id",
        )
        await check_batches(
            database.sources.search_documents if searching else database.sources.list_documents,
            SearchDocumentsRequest(**common, query=query, filter_=DocumentListFilter(library=library))
            if searching else DocumentListRequest(**common, filter_=DocumentListFilter(library=library)),
            documents, "source_id",
        )
        await check_batches(
            database.sources.search_pages if searching else database.sources.list_pages,
            SearchPagesRequest(**common, query=query, filter_=PageListFilter(library=library))
            if searching else PageListRequest(**common, filter_=PageListFilter(library=browse_filters["scans"])),
            pages, "source_id",
        )
    # Canonical document scope also exceeds a batch, without any implicit face filter.
    gallery = first.documents["page-gallery"]
    initial = await database.sources.list_pages(PageListRequest(
        limit=12, filter_=PageListFilter(document_source_id=[gallery]),
    ))
    assert len(initial.items) == 12 and initial.cursor is not None
    final = await database.sources.list_pages(PageListRequest(
        limit=12, cursor=initial.cursor, filter_=PageListFilter(document_source_id=[gallery]),
    ))
    assert len(final.items) == 2 and final.cursor is None
    assert first.filter_examples["pagination-scoped-scans"] == f"/scans?document={gallery}"
    for key in ("pagination-people", "pagination-scans", "pagination-documents"):
        assert parse_qs(urlsplit(first.filter_examples[key]).query)["q"] == ["Pagination"]
    page = await database.sources.get_page(first.pages[keys[-1]])
    image = await get_page_image(page.library, page.document_id, page.page_id, max_width=256)
    with Image.open(io.BytesIO(image.content)) as stored:
        assert stored.width == 256
    actor = GenericActor(user_id=first.users["reviewer"])
    edited = await database.entities.patch(first.entities[keys[0]], EntityPatchRequest(name="Reviewed pagination"), actor)
    mention = await database.text_mentions.patch(first.mentions[keys[0]], TextMentionPatchRequest(entity_id=None), actor)
    edited = await database.entities.get(edited.entity_id)
    second = await preview.seed_preview(database, filesystem)
    assert second == first
    assert (await database.entities.get(edited.entity_id)).last_touched_at == edited.last_touched_at
    assert (await database.text_mentions.get(mention.mention_id)).entity_id is None


@pytest.mark.asyncio
async def test_global_discovery_outside_retained_workspace(seed_target):
    from people_gator_api.schemas.search import EntitySearchQuery
    from people_gator_api.seeding.fixtures import DISCOVERY_MODEL

    db, filesystem, _ = seed_target
    first = await preview.seed_preview(db, filesystem)
    example = urlsplit(first.filter_examples['global-discovery'])
    scope = parse_qs(example.query)
    reference = first.entities['discovery']
    assert example.path == f'/people/{reference}'
    assert scope['library'] == ['preview-mzk']
    assert scope['document'] == [str(first.documents['discovery'])]
    assert scope['page'] == [str(first.pages['discovery-1'])]
    assert scope['link_state'] == ['verified']
    assert scope['touched_by'] == [str(first.users['reviewer'])]
    assert scope['api_key'] == [str(first.api_keys['ocr'])]
    query = EntitySearchQuery(entity_id=reference, entity_annotations=scope['discovery_annotations'],
                              face_embedding_model=scope['discovery_model'][0])
    assert query.face_embedding_model == DISCOVERY_MODEL
    scan = parse_qs(urlsplit(first.filter_examples['global-discovery-scan']).query)
    assert scan['candidate_mode'] == ['face']
    assert scan['person'] == [str(first.faces['discovery-reference-0'])]
    scan_matches = await db.entities.search(SearchEntitiesRequest(limit=50, query=QueryBase(
        face_id=[first.faces['discovery-reference-0']], face_embedding_model=DISCOVERY_MODEL)))
    assert first.entities['discovery-face'] in {item.entity_id for item in scan_matches.items}
    excluded = parse_qs(urlsplit(first.filter_examples['global-discovery-scan-excluded']).query)
    reference_face = await db.faces.get(uuid.UUID(excluded['person'][0]))
    assert reference_face is not None
    assert reference_face.embeddings == [DISCOVERY_MODEL]
    hidden = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(
        source_id=[reference_face.source_id], last_touched_by_user_id=excluded['touched_by'])))
    assert reference_face.detection_id not in {face.detection_id for face in hidden.items}
    assert first.entities['discovery-face'] in {item.entity_id for item in scan_matches.items}
    page_example = urlsplit(first.filter_examples['scan-page-entities'])
    page_scope = parse_qs(page_example.query)
    reference_page = await db.sources.get_page(first.pages['discovery-1'])
    assert reference_page is not None
    assert page_example.path.endswith('/pages/' + str(reference_page.page_id))
    assert page_scope['candidate_mode'] == ['page']
    assert page_scope['link_state'] == ['verified']
    assert page_scope['touched_by'] == [str(first.users['reviewer'])]
    on_page = await db.entities.list(EntityListRequest(limit=100,
        filter_=EntityListFilter(source_id=[first.pages['discovery-1']])))
    assert {item.entity_id for item in on_page.items} == {reference}
    page_faces = await db.faces.list(FaceListRequest(limit=100,
        filter_=FaceListFilter(source_id=[first.pages['discovery-1']])))
    assert reference_face.detection_id in {face.detection_id for face in page_faces.items}
    text_scope = parse_qs(urlsplit(first.filter_examples['scan-global-text']).query)
    assert 'person' not in text_scope  # Text lookup needs no selected face.
    text_matches = await db.entities.search(SearchEntitiesRequest(limit=50,
        query=QueryBase(text=text_scope['candidate_text'])))
    assert first.entities['discovery-face'] in {item.entity_id for item in text_matches.items}
    scoped_matches = await db.entities.search(SearchEntitiesRequest(limit=50,
        query=QueryBase(text=text_scope['candidate_text']), filter_=EntityListFilter(
            library=text_scope['library'], last_touched_by_user_id=text_scope['touched_by'])))
    assert first.entities['discovery-face'] not in {item.entity_id for item in scoped_matches.items}
    assigned_id = first.faces['discovery-global-assigned']
    unassigned_id = first.faces['discovery-global-unassigned']
    candidate_id = first.entities['discovery-face']
    # These are actual cross-library/document/page candidates, with local media.
    page = await db.sources.get_page(first.pages['discovery-global-1'])
    assert page.library == 'preview-nlk'
    assert page.source_id != first.pages['discovery-1']
    for face_id in (assigned_id, unassigned_id):
        face = await db.faces.get(face_id)
        assert face.source_id == page.source_id
        crop = await get_aligned_face_crop(first.users['reviewer'], face, page, max_width=128)
        with Image.open(io.BytesIO(crop.content)) as image:
            assert image.size == (128, 128)
    people = await db.entities.search(SearchEntitiesRequest(limit=40, query=query))
    faces = await db.faces.search(SearchFacesRequest(limit=40, query=query))
    assert candidate_id in {item.entity_id for item in people.items}
    assert {assigned_id, unassigned_id} <= {item.detection_id for item in faces.items}
    # Each individual inherited source predicate would wrongly hide both.
    for field, value in (('library', ['preview-mzk']),
                         ('document_source_id', [first.documents['discovery']]),
                         ('page_source_id', [first.pages['discovery-1']])):
        local_faces = await db.faces.search(SearchFacesRequest(
            limit=40, query=query, filter_=FaceListFilter(**{field: value})))
        assert not {assigned_id, unassigned_id} & {item.detection_id for item in local_faces.items}
    # The duplicate person has no evidence on the locally selected reference page.
    local_people = await db.entities.search(SearchEntitiesRequest(
        limit=40, query=query, filter_=EntityListFilter(page_source_id=[first.pages['discovery-1']])))
    assert candidate_id not in {item.entity_id for item in local_people.items}
    actor = GenericActor(user_id=first.users['reviewer'])
    reviewed = await db.faces.patch(unassigned_id, FacePatchRequest(entity_id=reference), actor)
    edited = await db.entities.patch(candidate_id, EntityPatchRequest(short_description='Reviewed global match'), actor)
    before_page = await db.sources.get_page(page.source_id)
    manifest = await filesystem.read_bytes(preview.MANIFEST_KEY)
    second = await preview.seed_preview(db, filesystem)
    assert second == first
    assert await db.faces.get(unassigned_id) == reviewed
    assert await db.entities.get(candidate_id) == edited
    assert await db.sources.get_page(page.source_id) == before_page
    assert await filesystem.read_bytes(preview.MANIFEST_KEY) == manifest


@pytest.mark.asyncio
async def test_deactivated_reviewer_keeps_attribution_across_reruns(seed_target: SeedTarget) -> None:
    from people_gator_api.schemas.entity_links import EntityLinkState
    from people_gator_api.schemas.mentions import TextMentionListFilter
    from people_gator_api.schemas.users import (
        UserListFilter, UserListRequest, UserPatchRequest, UserResponse,
    )

    db, fs, _ = seed_target

    async def user(user_id: uuid.UUID) -> UserResponse:
        found = await db.users.get(user_id)
        assert found is not None
        return found

    seed = await preview.seed_preview(db, fs)
    former = await user(seed.users["former"])
    assert not former.is_active
    assert "former" not in seed.api_keys
    mention = await db.text_mentions.get(seed.mentions["deactivated-olga-mention"])
    assert mention is not None
    assert mention.entity_id == seed.entities["deactivated-olga"]
    assert mention.last_touched_by_user_id == former.user_id
    assert mention.last_touched_by_api_key_id is None
    touched = await db.text_mentions.list(TextMentionListRequest(
        limit=10, filter_=TextMentionListFilter(last_touched_by_user_id=[former.user_id]),
    ))
    assert [item.mention_id for item in touched.items] == [mention.mention_id]
    example = parse_qs(urlsplit(seed.filter_examples["deactivated-reviewer"]).query)
    assert example["touched_by"] == [str(former.user_id)]
    options = await db.users.list(UserListRequest(limit=10, filter_=UserListFilter(search="former")))
    assert [option.user_id for option in options.items] == [former.user_id]

    # A reviewer verifies the link; an administrator later reactivates the user.
    reviewed = await db.text_mentions.patch(
        mention.mention_id, TextMentionPatchRequest(entity_link_state=EntityLinkState.verified),
        GenericActor(user_id=seed.users["reviewer"]),
    )
    assert reviewed is not None
    await db.users.patch(former.user_id, UserPatchRequest(is_active=True))
    again = await preview.seed_preview(db, fs)
    assert again.users["former"] == former.user_id
    assert (await user(former.user_id)).is_active
    kept = await db.text_mentions.get(mention.mention_id)
    assert kept is not None
    assert kept.entity_link_state == EntityLinkState.verified
    assert kept.last_touched_at == reviewed.last_touched_at
    assert kept.last_touched_by_user_id == seed.users["reviewer"]

    # Seeding never reactivates (or deactivates) an existing identity.
    await db.users.patch(former.user_id, UserPatchRequest(is_active=False))
    await preview.seed_preview(db, fs)
    assert not (await user(former.user_id)).is_active


@pytest.mark.asyncio
async def test_bearer_lifecycle_uses_token_identity_without_auth_lookups(
    seed_target: SeedTarget, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    from dataclasses import dataclass
    from types import TracebackType

    import argon2
    import httpx
    from fastapi import FastAPI
    from people_gator_api.routes.jwks import router as token_router
    from people_gator_api.routes.v1 import router
    from people_gator_api.schemas.users import (
        UserListFilter, UserListRequest, UserPatchRequest, UserResponse,
    )
    from people_gator_api.services import auth_service, database_service, jwk_service
    from people_gator_api.settings import JwkSettings, LocalStorageSettings, StorageSettings

    db, fs, _ = seed_target
    seed = await preview.seed_preview(db, fs)
    monkeypatch.setattr(settings, "storage", StorageSettings(local=LocalStorageSettings(root=tmp_path)))
    monkeypatch.setattr(settings, "jwk", JwkSettings(
        users_path="auth/users.json", key_path="auth/jwks.json",
        issuer=jwk_service.TOKEN_ISSUER, audience=jwk_service.TOKEN_AUDIENCE,
    ))
    monkeypatch.setattr(auth_service, "_refresh_sessions", {})
    monkeypatch.setattr(auth_service, "_refresh_session_locks", {})
    monkeypatch.setattr(jwk_service, "_keyset", None)
    monkeypatch.setattr(jwk_service, "_last_fetch_time", None)
    monkeypatch.setattr(jwk_service, "_keyset_lock", asyncio.Lock())
    monkeypatch.setattr(jwk_service, "_access_claims_registry", None)
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth/users.json").write_text(json.dumps({"lifecycle": {
        "hash": argon2.PasswordHasher().hash("synthetic"),
        "scopes": ["people-gator:browse", "people-gator:annotate"],
    }}))

    @dataclass
    class CountedContext:
        """Counts database scopes entered through get_database_context()."""

        entries: int = 0

        def __call__(self) -> "CountedContext":
            return self

        async def __aenter__(self) -> Database:
            self.entries += 1
            return db

        async def __aexit__(
            self, exc_type: type[BaseException] | None, exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            return None

    async def whoami(actor: auth_service.BrowseActorDependency) -> dict[str, str]:
        return {"user_id": str(actor.user_id)}

    contexts = CountedContext()
    app = FastAPI()
    app.include_router(token_router)
    app.include_router(router)
    app.add_api_route("/whoami", whoami)
    app.dependency_overrides[database_service.get_database] = lambda: db
    app.dependency_overrides[database_service.get_database_context] = contexts
    login_form = {"username": "lifecycle", "password": "synthetic",
                  "scope": "people-gator:browse people-gator:annotate"}

    async def identities() -> list[UserResponse]:
        return (await db.users.list(UserListRequest(limit=10, filter_=UserListFilter(
            external_subject=["lifecycle"], external_issuer=[settings.jwk.issuer],
        )))).items

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert await identities() == []
        login = await client.post("/token/login", data=login_form)
        assert login.status_code == 200, login.text
        assert contexts.entries == 1
        [user] = await identities()
        assert user.is_active
        tokens = TokenResponse.model_validate(login.json())
        claims = await jwk_service.verify_access_token(tokens.access_token)
        assert claims["uid"] == user.user_id
        bearer = {"Authorization": "Bearer " + tokens.access_token}

        for _ in range(2):
            response = await client.get("/whoami", headers=bearer)
            assert response.json() == {"user_id": str(user.user_id)}
        olga = f"/api/v1/entities/{seed.entities['deactivated-olga']}"
        patched = await client.patch(olga, json={"short_description": "Checked by lifecycle."}, headers=bearer)
        assert patched.status_code == 200, patched.text
        assert patched.json()["last_touched_by_user_id"] == str(user.user_id)
        assert patched.json()["last_touched_by_api_key_id"] is None
        assert contexts.entries == 1

        await db.users.patch(user.user_id, UserPatchRequest(is_active=False))
        # Issued access tokens remain valid until expiry, including profile reads.
        assert (await client.get("/whoami", headers=bearer)).status_code == 200
        me = await client.get("/api/v1/me", headers=bearer)
        assert me.status_code == 200 and me.json()["is_active"] is False
        patched = await client.patch(olga, json={"short_description": "Written after deactivation."}, headers=bearer)
        assert patched.json()["last_touched_by_user_id"] == str(user.user_id)
        assert contexts.entries == 1

        assert (await client.post("/token/login", data=login_form)).status_code == 403
        refused = await client.post("/token/refresh", json={"refresh_token": tokens.refresh_token})
        assert refused.status_code == 403
        assert "access_token" not in refused.json()
        await db.users.patch(user.user_id, UserPatchRequest(is_active=True))
        # The rejected refresh revoked its session; reactivation does not revive it.
        revoked = await client.post("/token/refresh", json={"refresh_token": tokens.refresh_token})
        assert revoked.status_code == 401
        assert [item.user_id for item in await identities()] == [user.user_id]

        relogin = TokenResponse.model_validate((await client.post("/token/login", data=login_form)).json())
        refreshed = await client.post("/token/refresh", json={"refresh_token": relogin.refresh_token})
        assert refreshed.status_code == 200
        renewed = TokenResponse.model_validate(refreshed.json())
        assert (await jwk_service.verify_access_token(renewed.access_token))["uid"] == user.user_id

        expires = claims["exp"]
        monkeypatch.setattr(jwk_service, "_now", lambda: expires + 1)
        monkeypatch.setattr(jwk_service, "_access_claims_registry", None)
        assert (await client.get("/whoami", headers=bearer)).status_code == 401


@pytest.mark.asyncio
async def test_document_table_summaries_are_scoped_batched_and_preserved(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.search import SearchDocumentsRequest
    from sqlalchemy import event

    database, filesystem, engine = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    statements = []
    def capture(conn, cursor, statement, params, context, executemany):
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        listed = await database.sources.list_documents(DocumentListRequest(limit=100))
        list_queries = len(statements)
        statements.clear()
        await database.sources.list_documents(DocumentListRequest(limit=1))
        assert len(statements) == list_queries  # No per-document query cascade.
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    document = next(item for item in listed.items if item.source_id == seeded.documents["table-ledger"])
    def summary(item):
        return (item.registered_page_count, item.linked_entity_count, item.entity_link_stats, item.first_page_source_id)
    assert document.registered_page_count == 2
    first_fixture = min((page for page in PAGES if page.document == "table-ledger"), key=lambda page: page.page_id)
    assert document.first_page_source_id == seeded.pages[first_fixture.key]
    # The preview is usable media and the same choice even under evidence filters.
    first_page = await database.sources.get_page(document.first_page_source_id)
    thumbnail = await get_page_image(first_page.library, first_page.document_id, first_page.page_id, max_width=256)
    with Image.open(io.BytesIO(thumbnail.content)) as image:
        assert image.width == 256
    assert document.linked_entity_count == 2
    assert document.entity_link_stats.faces.model_dump() == dict(total=4, automatic=1, manual=1, verified=1, unassigned=1)
    assert document.entity_link_stats.mentions.model_dump() == dict(total=5, automatic=2, manual=1, verified=1, unassigned=1)
    assert document.last_touched_by_user_id == seeded.users["importer"]
    assert document.last_touched_by_api_key_id == seeded.api_keys["importer"]
    assert document.last_touched_by_user_name == "Preview face importer"
    assert document.last_touched_by_api_key_name == "Preview face importer"
    for key in ("table-mirror", "empty-document"):
        empty = next(item for item in listed.items if item.source_id == seeded.documents[key])
        assert empty.registered_page_count == empty.linked_entity_count == 0
        assert empty.entity_link_stats.faces.total == empty.entity_link_stats.mentions.total == 0
        assert empty.last_touched_at is None
        assert empty.first_page_source_id is None
    filtered = await database.sources.list_documents(DocumentListRequest(
        limit=100, filter_=DocumentListFilter(entity_link_state=["verified"], library=["preview-table"]),
    ))
    assert [item.source_id for item in filtered.items] == [document.source_id]
    assert summary(filtered.items[0]) == summary(document)
    scored = await database.sources.search_documents(SearchDocumentsRequest(limit=100, query=QueryBase(text=["Document table ledger"])))
    found = next(item for item in scored.items if item.source_id == document.source_id)
    assert summary(found) == summary(document)
    assert found.last_touched_by_user_name == document.last_touched_by_user_name
    reviewer = next(item for item in listed.items if item.source_id == seeded.documents["issue8-direct"])
    assert reviewer.last_touched_by_user_name == "Preview reviewer"
    assert reviewer.last_touched_by_api_key_id is reviewer.last_touched_by_api_key_name is None
    # Rerunning adds nothing and does not retouch the aggregate attribution.
    await preview.seed_preview(database, filesystem)
    again = await database.sources.get_document(document.source_id)
    assert summary(again) == summary(document)
    assert again.last_touched_at == document.last_touched_at

    # Annotation edits/deletes update summaries and the same recorded actor.
    from people_gator_api.services.auth_service import AuthContext
    reviewer_actor = AuthContext(
        user_id=seeded.users["reviewer"], authentication_method="bearer",
        scopes={"people-gator:annotate"},
    )
    await database.faces.delete(seeded.faces["table-manual"], context=reviewer_actor)
    await database.text_mentions.delete(seeded.mentions["table-manual-mention"], context=reviewer_actor)
    edited = await database.sources.get_document(document.source_id)
    assert edited.linked_entity_count == 1  # Repeated Tereza links still count once.
    assert edited.entity_link_stats.faces.total == 3
    assert edited.entity_link_stats.mentions.total == 4
    assert edited.last_touched_by_user_id == reviewer_actor.user_id
    assert edited.last_touched_by_user_name == "Preview reviewer"
    assert edited.last_touched_by_api_key_id is edited.last_touched_by_api_key_name is None
    await preview.seed_preview(database, filesystem)
    assert await database.sources.get_document(document.source_id) == edited


@pytest.mark.asyncio
@pytest.mark.parametrize("example,direction", [("document-table-sort", "desc"), ("document-table-scroll", "asc")])
async def test_document_table_sort_example_uses_server_cursor_order(seed_target, example, direction):
    from people_gator_api.schemas.sources import DocumentListFilter
    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    assert seeded.filter_examples["document-table-scroll"] == seeded.filter_examples["document-table-scroll-performance"] == seeded.filter_examples["document-table-page-header"] == seeded.filter_examples["document-table-sticky-header"]
    demo = parse_qs(urlsplit(seeded.filter_examples[example]).query)
    assert "view" not in demo
    query = DocumentListRequest(
        limit=12, return_total_count=True,
        filter_=DocumentListFilter(library=demo["library"]),
        sort=demo["sort"][0], sort_direction=demo.get("dir", ["asc"])[0],
    )
    first = await database.sources.list_documents(query)
    second = await database.sources.list_documents(query.model_copy(update={"cursor": first.cursor}))
    assert first.total_count == 14 and len(first.items) == 12 and first.cursor
    assert len(second.items) == 2 and second.cursor is None
    assert [item.name for item in [*first.items, *second.items]] == [
        f"Pagination ledger {i:02}" for i in (range(14, 0, -1) if direction == "desc" else range(1, 15))
    ]


@pytest.mark.asyncio
async def test_document_table_unnamed_link_resolves_and_preserves_identity(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    demo = parse_qs(urlsplit(seeded.filter_examples["document-table-unnamed"]).query)
    assert "view" not in demo
    result = await database.sources.list_documents(DocumentListRequest(
        limit=12, filter_=DocumentListFilter(source_id=demo["document"]),
    ))
    assert len(result.items) == 1
    document = result.items[0]
    assert document.source_id == seeded.documents["legacy-document"]
    assert not document.name
    assert document.document_id and document.library == "preview-mzk"
    assert document.registered_page_count > 0 and document.first_page_source_id
    page = await database.sources.get_page(document.first_page_source_id)
    assert (page.library, page.document_id) == (document.library, document.document_id)
    await preview.seed_preview(database, filesystem)
    reviewed = await database.sources.get_document(document.source_id)
    assert reviewed.name is None
    assert reviewed.source_id == document.source_id
    assert reviewed.document_id == document.document_id
    assert reviewed.first_page_source_id == document.first_page_source_id


@pytest.mark.asyncio
async def test_document_table_default_link_has_usable_rows_and_media(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    url = urlsplit(seeded.filter_examples["document-table"])
    query = parse_qs(url.query)
    assert url.path == "/documents" and "view" not in query
    rows = await database.sources.list_documents(DocumentListRequest(
        limit=12, filter_=DocumentListFilter(library=query["library"]),
    ))
    assert [row.source_id for row in rows.items] == [seeded.documents["table-ledger"]]
    row = rows.items[0]
    assert row.name == "Document table ledger" and row.registered_page_count == 2
    page = await database.sources.get_page(row.first_page_source_id)
    image = await get_page_image(page.library, page.document_id, page.page_id, max_width=256)
    assert image.content
    await preview.seed_preview(database, filesystem)
    assert await database.sources.get_document(row.source_id) == row


@pytest.mark.asyncio
@pytest.mark.parametrize("direction", ["asc", "desc"])
async def test_document_table_unknown_name_sorts_at_directional_edge(seed_target, direction):
    import unicodedata
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.search import SearchDocumentsRequest

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    demo = parse_qs(urlsplit(seeded.filter_examples["document-table-unknown-names"]).query)
    scope = DocumentListFilter(library=demo["library"])
    request = DocumentListRequest(limit=2, filter_=scope, sort=demo["sort"][0], sort_direction=direction)
    rows, cursor = [], None
    while True:
        batch = await database.sources.list_documents(request.model_copy(update={"cursor": cursor}))
        rows.extend(batch.items)
        cursor = batch.cursor
        if cursor is None:
            break
    def key(row):
        title = row.name or ""
        normalized = "".join(char for char in unicodedata.normalize("NFD", title) if not unicodedata.combining(char)).lower()
        return normalized, title
    expected = sorted(sorted(rows, key=lambda row: row.source_id.int), key=key, reverse=direction == "desc")
    assert [row.source_id for row in rows] == [row.source_id for row in expected]
    position = next(i for i, row in enumerate(rows) if row.source_id == seeded.documents["legacy-document"])
    assert position == (0 if direction == "asc" else len(rows) - 1)
    assert rows[position].name is None
    search = await database.sources.search_documents(SearchDocumentsRequest(
        limit=100, filter_=scope, query=QueryBase(text=demo["library"]), sort="name", sort_direction=direction,
    ))
    assert [row.source_id for row in search.items] == [row.source_id for row in rows]
    await preview.seed_preview(database, filesystem)
    assert (await database.sources.get_document(seeded.documents["legacy-document"])).name is None


@pytest.mark.asyncio
async def test_document_table_ndk_column_keeps_canonical_source_and_optional_media(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter, document_url

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    assert seeded.filter_examples["document-table-ndk-column"] == seeded.filter_examples["document-table-ndk-link"]
    query = parse_qs(urlsplit(seeded.filter_examples["document-table-ndk-column"]).query)
    rows = await database.sources.list_documents(DocumentListRequest(
        limit=12, filter_=DocumentListFilter(source_id=query["document"]),
    ))
    assert len(rows.items) == 1
    row = rows.items[0]
    assert row.source_id == seeded.documents["table-ledger"]
    assert str(row.url) == document_url(row.library, row.document_id)
    page = await database.sources.get_page(row.first_page_source_id)
    assert (page.library, page.document_id) == (row.library, row.document_id)
    image = await get_page_image(page.library, page.document_id, page.page_id, max_width=256)
    assert image.content
    await preview.seed_preview(database, filesystem)
    assert await database.sources.get_document(row.source_id) == row


@pytest.mark.asyncio
async def test_document_table_annotation_groups_have_independent_full_scope_counts(seed_target):
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.search import SearchDocumentsRequest

    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    query = parse_qs(urlsplit(seeded.filter_examples["document-table-annotation-groups"]).query)
    scope = DocumentListFilter(library=query["library"])
    listed = await database.sources.list_documents(DocumentListRequest(limit=12, filter_=scope))
    searched = await database.sources.search_documents(SearchDocumentsRequest(
        limit=12, filter_=scope, query=QueryBase(text=query["library"]),
    ))
    expected = {
        seeded.documents["table-ledger"]: {
            "faces": dict(total=4, automatic=1, manual=1, verified=1, unassigned=1),
            "mentions": dict(total=5, automatic=2, manual=1, verified=1, unassigned=1),
        },
        seeded.documents["table-mirror"]: {kind: dict(total=0, automatic=0, manual=0, verified=0, unassigned=0) for kind in ("faces", "mentions")},
    }
    for response in (listed, searched):
        assert {row.source_id: row.entity_link_stats.model_dump() for row in response.items} == expected
    stats = expected[seeded.documents["table-ledger"]]
    assert {state: stats["faces"][state] + stats["mentions"][state] for state in stats["faces"]} == dict(total=9, automatic=3, manual=2, verified=2, unassigned=2)
    await preview.seed_preview(database, filesystem)
    again = await database.sources.list_documents(DocumentListRequest(limit=12, filter_=scope))
    assert again.items == listed.items


@pytest.mark.asyncio
async def test_archive_links_use_each_evidence_page_and_containing_document(seed_target):
    from people_gator_api.schemas.search import EntitySearchQuery
    from people_gator_api.seeding.fixtures import DISCOVERY_MODEL

    db, filesystem, _ = seed_target
    first = await preview.seed_preview(db, filesystem)
    person = await db.entities.get(first.entities["provenance-review"])
    assert person.thumbnail_face_id in {
        face.detection_id for face in (await db.faces.list(FaceListRequest(
            limit=100, filter_=FaceListFilter(entity_id=[person.entity_id]),
        ))).items
    }
    faces_path = urlsplit(first.filter_examples["archive-links-faces"])
    assert faces_path.path == f"/people/{person.entity_id}"
    assert parse_qs(faces_path.query)["origin_matched_face"] == [str(first.faces["provenance-auto"])]
    hits = await db.faces.search(SearchFacesRequest(limit=40, query=EntitySearchQuery(
        entity_id=first.entities["discovery"], entity_annotations=["faces"],
        face_embedding_model=DISCOVERY_MODEL,
    )))
    outside = {first.faces["discovery-global-assigned"], first.faces["discovery-global-unassigned"]}
    assert outside <= {face.detection_id for face in hits.items}
    for face in hits.items:
        page = await db.sources.get_page(face.source_id)
        document = await db.sources.lookup_document(DocumentLookupRequest(
            library=page.library, document_id=page.document_id,
        ))
        assert str(page.url) == f"{document.url}?page=uuid:{page.page_id}"
        assert not urlsplit(str(document.url)).query
        if face.detection_id in outside:
            assert page.library == "preview-nlk"
    page = await db.sources.get_page(first.pages["discovery-1"])
    assert first.filter_examples["archive-links-scan"].endswith(f"/pages/{page.page_id}")
    before = await db.entities.get(person.entity_id)
    assert await preview.seed_preview(db, filesystem) == first
    assert await db.entities.get(person.entity_id) == before


@pytest.mark.asyncio
@pytest.mark.parametrize("review_action", ["verify", "reassign"])
async def test_detection_actions_review_and_delete_survive_rerun(seed_target, review_action):
    database, filesystem, _ = seed_target
    seeded = await preview.seed_preview(database, filesystem)
    linked_id = seeded.faces["actions-linked"]
    false_id = seeded.faces["actions-false-positive"]
    linked = await database.faces.get(linked_id)
    false = await database.faces.get(false_id)
    assert linked.entity_id == seeded.entities["actions"]
    assert linked.entity_link_state == "automatic"
    assert false.entity_id is None and not false.embeddings
    source = await database.sources.get_page(linked.source_id)
    content = await get_page_image(source.library, source.document_id, source.page_id)
    with Image.open(io.BytesIO(content.content)) as image:
        assert image.size == (800, 1100)
    actor = await database.users.get(seeded.users["reviewer"])
    query = parse_qs(urlsplit(seeded.filter_examples["detection-actions"]).query)
    assert query["person"] == [str(linked_id)]
    assert urlsplit(seeded.filter_examples["detection-actions"]).path == (
        f"/libraries/{source.library}/documents/{source.document_id}/pages/{source.page_id}"
    )
    patch = (
        FacePatchRequest(entity_link_state="verified") if review_action == "verify"
        else FacePatchRequest(entity_id=seeded.entities["ada"], entity_link_state="manual")
    )
    reviewed = await database.faces.patch(linked_id, patch, actor)
    await database.faces.delete(false_id, context=actor)
    rerun = await preview.seed_preview(database, filesystem)
    assert "actions-false-positive" not in rerun.faces
    assert await database.faces.get(false_id) is None
    faces = await database.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(source_id=[linked.source_id])))
    assert [face.detection_id for face in faces.items] == [linked_id]
    assert await database.faces.get(linked_id) == reviewed
    assert rerun.filter_examples["detection-actions"] == seeded.filter_examples["detection-actions"]


@pytest.mark.asyncio
async def test_identity_reference_gallery_pages_cross_library_crops_and_preserves_review(seed_target):
    database, filesystem, _ = seed_target
    seed = await preview.seed_preview(database, filesystem)
    # One link covers the gallery, compact layout, dismissal and action row.
    assert not [key for key in seed.filter_examples
                if key.startswith('identity-reference-')
                and key not in {'identity-reference-faces', 'identity-reference-empty', 'identity-reference-scroll'}]
    action_query = parse_qs(urlsplit(seed.filter_examples['identity-reference-faces']).query)
    assert action_query['person'] == [str(seed.faces['reference-ada-manual'])]
    assert (await database.faces.get(seed.faces['reference-ada-manual'])).entity_link_state == 'manual'
    ada = seed.entities['ada']
    expected = {
        seed.faces[face.key]
        for page in PAGES for face in page.faces if face.person == 'ada'
    }
    items = []
    cursor = None
    while True:
        page = await database.faces.list(FaceListRequest(
            filter_=FaceListFilter(entity_id=[ada]), limit=6,
            return_total_count=True, sort='detection_id', sort_direction='asc', cursor=cursor,
        ))
        assert page.total_count == len(expected)
        items.extend(page.items)
        if page.cursor is None:
            break
        assert page.cursor != cursor
        cursor = page.cursor
    assert len(items) > 6
    assert len(items) == len({face.detection_id for face in items})
    assert {face.detection_id for face in items} == expected
    assert all(face.entity_id == ada for face in items)
    assert {face.entity_link_state for face in items} == {'automatic', 'manual', 'verified'}
    sources = [await database.sources.get_page(face.source_id) for face in items]
    assert {source.library for source in sources} == {'preview-mzk', 'preview-nlk'}
    assert len({source.document_id for source in sources}) > 1
    for face in items:
        source = await database.sources.lookup(GenericSourceLookupRequest(source_id=face.source_id))
        crop = await get_aligned_face_crop(seed.users["reviewer"], face, source, max_width=96)
        with Image.open(io.BytesIO(crop.content)) as image:
            assert image.width == image.height == 96
    nora = await database.faces.list(FaceListRequest(limit=6, filter_=FaceListFilter(entity_id=[seed.entities['nora']])))
    assert nora.items == []
    assert seed.faces['reference-emil'] not in expected
    assert seed.faces['unassigned-ada'] not in expected

    scroll_query = parse_qs(urlsplit(seed.filter_examples['identity-reference-scroll']).query)
    assert scroll_query['person'] == [str(seed.faces['discovery-reference-0'])]
    scroll_faces = []
    cursor = None
    while True:
        batch = await database.faces.list(FaceListRequest(
            filter_=FaceListFilter(entity_id=[seed.entities['discovery']]),
            limit=6, return_total_count=True, sort='detection_id', cursor=cursor,
        ))
        assert batch.total_count == 15
        scroll_faces.extend(batch.items)
        if batch.cursor is None:
            break
        assert batch.cursor != cursor
        cursor = batch.cursor
    assert len(scroll_faces) == len({face.detection_id for face in scroll_faces}) == 15
    assert all(face.entity_id == seed.entities['discovery'] for face in scroll_faces)

    actor = GenericActor(user_id=seed.users['reviewer'])
    reviewed = await database.faces.patch(
        seed.faces['reference-ada-manual'], FacePatchRequest(entity_id=None, entity_link_state=None), actor,
    )
    before = await database.entities.get(ada)
    rerun = await preview.seed_preview(database, filesystem)
    assert rerun.faces == seed.faces
    assert (await database.faces.get(reviewed.detection_id)) == reviewed
    assert (await database.entities.get(ada)).last_touched_at == before.last_touched_at
    linked = await database.faces.list(FaceListRequest(filter_=FaceListFilter(entity_id=[ada]), limit=100))
    assert {face.detection_id for face in linked.items} == expected - {reviewed.detection_id}


@pytest.mark.asyncio
async def test_person_review_groups_candidates_and_preservation(seed_target):
    from people_gator_api.schemas.mentions import TextMentionGroupListRequest, TextMentionListFilter
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    person = seed.entities['review']
    assert seed.filter_examples['person-review-overflow-card'] == f'/people/{person}'
    assert seed.filter_examples['person-review-loading'] == f'/people/{person}?tab=mentions&mention_view=document'
    assert seed.filter_examples['person-review-shift-selection'] == f'/people/{person}?tab=mentions&mention_view=page'
    assert seed.filter_examples['person-review-compact'] == f'/people/{person}?tab=mentions&mention_view=groups&mention_density=compact'
    faces = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(entity_id=[person])))
    assert len(faces.items) == 42
    assert {face.entity_link_state.value for face in faces.items} == {'automatic', 'manual', 'verified'}
    scope = TextMentionListFilter(entity_id=[person])
    for mode, expected in [('mention', 1), ('document', 3), ('page', 9)]:
        groups = await db.text_mentions.list_groups(TextMentionGroupListRequest(
            limit=20, group_by=mode, filter_=scope))
        assert len(groups.items) == expected
        assert sum(group.occurrence_count for group in groups.items) == 27
        if mode == 'page':
            assert all(g.occurrence_count == 3 for g in groups.items)
            # Same-titled documents never interleave, including across cursor pages.
            for sort in ({}, {'sort': 'text', 'sort_direction': 'desc'}, {'sort': 'count'}):
                paged, cursor = [], None
                while True:
                    batch = await db.text_mentions.list_groups(TextMentionGroupListRequest(
                        limit=2, group_by=mode, filter_=scope, cursor=cursor, **sort))
                    paged.extend(batch.items)
                    if not (cursor := batch.cursor):
                        break
                documents = [(g.library, g.document_id) for g in paged]
                runs = [d for i, d in enumerate(documents) if i == 0 or documents[i - 1] != d]
                assert len(paged) == 9 and len(runs) == len(set(runs)) == 3
        if mode == 'document':
            assert [g.name for g in groups.items].count('Review ledger') == 2
            assert len({g.source_id for g in groups.items}) == 3
            assert all(g.library and g.document_id for g in groups.items)
    candidates = await db.faces.search(SearchFacesRequest(limit=100,
        query=QueryBase(face_id=[faces.items[0].detection_id], face_embedding_model=MODEL)))
    assert {seed.faces['review-unassigned'], seed.faces['review-candidate']} <= {f.detection_id for f in candidates.items}
    # The exact group exceeds the occurrence batch. A review edit survives reseeding.
    mentions = await db.text_mentions.list(TextMentionListRequest(limit=20, return_total_count=True, filter_=scope))
    assert mentions.total_count == 27 and mentions.cursor
    assert all(m.last_touched_at and m.last_touched_by_user_id for m in mentions.items)
    remainder = await db.text_mentions.list(TextMentionListRequest(limit=20, cursor=mentions.cursor, return_total_count=True, filter_=scope))
    assert len(remainder.items) == 7
    assert not ({m.mention_id for m in mentions.items} & {m.mention_id for m in remainder.items})
    actor = GenericActor(user_id=seed.users['reviewer'])
    edited = await db.text_mentions.patch(mentions.items[0].mention_id, TextMentionPatchRequest(entity_id=None), actor)
    again = await preview.seed_preview(db, filesystem)
    assert again.mentions == seed.mentions
    assert await db.text_mentions.get(edited.mention_id) == edited
    groups = await db.text_mentions.list_groups(TextMentionGroupListRequest(limit=10, filter_=scope))
    assert groups.items[0].occurrence_count == 26


@pytest.mark.asyncio
async def test_person_review_overflow_upgrade_recovers_without_resetting_edits(seed_target, monkeypatch):
    db, filesystem, _ = seed_target
    all_pages = preview.PAGES
    monkeypatch.setattr(preview, 'PAGES', tuple(p for p in all_pages if not p.key.startswith('review-overflow-')))
    first = await preview.seed_preview(db, filesystem)
    actor = GenericActor(user_id=first.users['reviewer'])
    edited = await db.faces.patch(first.faces['review-face-0-0'], FacePatchRequest(entity_id=None), actor)
    monkeypatch.setattr(preview, 'PAGES', all_pages)
    original_write = filesystem.write_bytes
    interrupted = False

    async def write(key, content):
        nonlocal interrupted
        if key == preview.MANIFEST_KEY and not interrupted and 'review-overflow-face-0-0' in json.loads(content)['faces']:
            interrupted = True
            raise OSError('interrupted overflow checkpoint')
        await original_write(key, content)

    monkeypatch.setattr(filesystem, 'write_bytes', write)
    with pytest.raises(OSError, match='overflow checkpoint'):
        await preview.seed_preview(db, filesystem)
    grown = await preview.seed_preview(db, filesystem)
    again = await preview.seed_preview(db, filesystem)
    assert grown.faces == again.faces
    assert all(grown.faces[key] == value for key, value in first.faces.items())
    assert len(grown.faces) - len(first.faces) == 24
    assert await counts(db) == (37, 119, 75)
    assert await db.faces.get(edited.detection_id) == edited
    linked = await db.faces.list(FaceListRequest(limit=100, filter_=FaceListFilter(entity_id=[grown.entities['review']])))
    assert len(linked.items) == 41
    for key in ('review-overflow-face-0-0', 'review-overflow-face-11-1'):
        face = await db.faces.get(grown.faces[key])
        source = await db.sources.get_page(face.source_id)
        crop = await get_aligned_face_crop(actor.user_id, face, source, max_width=128)
        assert crop.content


@pytest.mark.asyncio
async def test_found_faces_assignment_pages_cover_the_complete_seed_candidates(seed_target):
    from people_gator_api.seeding.fixtures import DISCOVERY_MODEL
    from people_gator_api.schemas.search import EntitySearchQuery
    db, filesystem, _ = seed_target
    seed = await preview.seed_preview(db, filesystem)
    person = seed.entities['review']
    assert 'people_annotations=all' in seed.filter_examples['person-review-found-faces']
    query = EntitySearchQuery(entity_id=person, entity_annotations=['faces'], face_embedding_model=DISCOVERY_MODEL)
    whole = await db.faces.search(SearchFacesRequest(limit=100, query=query, return_total_count=True))
    assert whole.total_count > 14
    assert all(face.entity_id != person for face in whole.items)
    partitions = []
    for assigned in (True, False):
        cursor, records, totals = None, [], set()
        while True:
            batch = await db.faces.search(SearchFacesRequest(limit=1 if not assigned else 3,
                query=query, filter_=FaceListFilter(is_assigned=assigned), cursor=cursor, return_total_count=True))
            records.extend(batch.items)
            totals.add(batch.total_count)
            cursor = batch.cursor
            if cursor is None:
                break
        assert len(totals) == 1 and totals.pop() == len(records)
        assert len({face.detection_id for face in records}) == len(records)
        assert all((face.entity_id is not None) is assigned for face in records)
        partitions.append({face.detection_id for face in records})
    assert not (partitions[0] & partitions[1])
    assert partitions[0] | partitions[1] == {face.detection_id for face in whole.items}
    assert seed.faces['review-unassigned'] in partitions[1]
    assert seed.faces['review-candidate'] in partitions[0]
    assert 'person-review-found-faces' in seed.filter_examples


@pytest.mark.asyncio
async def test_annotation_count_matrix_orders_filters_and_pages_before_cursors(
    seed_target,
):
    """All 15 numeric keys, both directions, both resources and bounded search."""
    from people_gator_api.schemas.annotation_counts import ANNOTATION_COUNT_FIELDS
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.schemas.search import (
        SearchDocumentsRequest,
        SearchPagesRequest,
    )
    from sqlalchemy import event

    db, fs, engine = seed_target
    seeded = await preview.seed_preview(db, fs)
    states = ("automatic", "manual", "verified", "unassigned")

    def counts(faces, mentions):
        result = {}
        for kind, values in (
            ("faces", faces),
            ("mentions", mentions),
            ("annotations", [a + b for a, b in zip(faces, mentions)]),
        ):
            result[f"{kind}_total_count"] = sum(values)
            result.update(
                {f"{kind}_{state}_count": value for state, value in zip(states, values)}
            )
        return result

    zero = [0, 0, 0, 0]
    expected_docs = {
        seeded.documents["count-faces"]: counts([1, 2, 1, 1], zero),
        seeded.documents["count-tie"]: counts([1, 1, 1, 1], zero),
        seeded.documents["count-mentions"]: counts(zero, [1, 1, 1, 1]),
        seeded.documents["count-empty"]: counts(zero, zero),
        # Direct mention + two pages, mirror shares archive identity only.
        seeded.documents["table-ledger"]: counts([1, 1, 1, 1], [2, 1, 1, 1]),
        seeded.documents["table-mirror"]: counts(zero, zero),
    }
    expected_pages = {
        seeded.pages["count-faces-1"]: counts([1, 1, 1, 1], zero),
        seeded.pages["count-faces-2"]: counts([0, 1, 0, 0], zero),
        seeded.pages["count-tie-1"]: counts([1, 1, 1, 1], zero),
        seeded.pages["count-mentions-1"]: counts(zero, [1, 1, 1, 1]),
        seeded.pages["count-empty-1"]: counts(zero, zero),
        seeded.pages["table-1"]: counts([1, 1, 0, 0], [1, 1, 0, 0]),
        seeded.pages["table-2"]: counts([0, 0, 1, 1], [0, 0, 1, 1]),
    }

    async def traverse(fetch, request, expected, **kwargs):
        rows, cursor = [], None
        while True:
            page = await fetch(
                request(limit=2, cursor=cursor, return_total_count=True, **kwargs)
            )
            assert page.total_count == len(expected)
            rows.extend(page.items)
            cursor = page.cursor
            if cursor is None:
                break
        assert len(rows) == len({row.source_id for row in rows}) == len(expected)
        assert {row.source_id for row in rows} == set(expected)
        # Count scopes also agree with the full response summaries.
        for row in rows:
            for field, value in expected[row.source_id].items():
                category, state, _ = field.split("_")
                stats = row.entity_link_stats
                actual = (
                    getattr(stats.faces, state) + getattr(stats.mentions, state)
                    if category == "annotations"
                    else getattr(getattr(stats, category), state)
                )
                assert actual == value
        return [row.source_id for row in rows]

    for expected, filter_type, request, search_request, fetch, search in (
        (
            expected_docs,
            DocumentListFilter,
            DocumentListRequest,
            SearchDocumentsRequest,
            db.sources.list_documents,
            db.sources.search_documents,
        ),
        (
            expected_pages,
            PageListFilter,
            PageListRequest,
            SearchPagesRequest,
            db.sources.list_pages,
            db.sources.search_pages,
        ),
    ):
        base = dict(source_id=list(expected))
        for field in ANNOTATION_COUNT_FIELDS:
            for direction in ("asc", "desc"):
                order = sorted(
                    expected,
                    key=lambda id: (
                        expected[id][field] * (1 if direction == "asc" else -1),
                        id.int,
                    ),
                )
                for method, req, extra in (
                    (fetch, request, {}),
                    (
                        search,
                        search_request,
                        {
                            "query": QueryBase(
                                text=[
                                    "preview-counts",
                                    "preview-table",
                                    "preview-table-mirror",
                                ]
                            )
                        },
                    ),
                ):
                    ids = await traverse(
                        method,
                        req,
                        expected,
                        filter_=filter_type(**base),
                        sort=field,
                        sort_direction=direction,
                        **extra,
                    )
                    assert ids == order
            for minimum in (0, 1, 2, 9_007_199_254_740_991):
                wanted = {
                    id: values
                    for id, values in expected.items()
                    if values[field] >= minimum
                }
                scope = filter_type(**base, **{f"min_{field}": minimum})
                await traverse(fetch, request, wanted, filter_=scope, sort=field)
                await traverse(
                    search,
                    search_request,
                    wanted,
                    filter_=scope,
                    sort=field,
                    query=QueryBase(
                        text=["preview-counts", "preview-table", "preview-table-mirror"]
                    ),
                )
        # Unset and zero preserve empty resources; implicit count direction is descending.
        assert await traverse(
            fetch,
            request,
            expected,
            filter_=filter_type(**base),
            sort="faces_total_count",
        ) == sorted(
            expected, key=lambda id: (-expected[id]["faces_total_count"], id.int)
        )
        # Multiple count minima AND evidence constraints, counts themselves stay resource-wide.
        wanted = {
            id: values
            for id, values in expected.items()
            if values["faces_manual_count"] >= 1
            and values["mentions_total_count"] >= 2
            and values["annotations_verified_count"] >= 1
        }
        await traverse(
            fetch,
            request,
            wanted,
            filter_=filter_type(
                **base,
                min_faces_manual_count=1,
                min_mentions_total_count=2,
                entity_link_state=["verified"],
            ),
            sort="annotations_verified_count",
        )
        first = await fetch(
            request(filter_=filter_type(**base), sort="faces_total_count", limit=1)
        )
        assert first.cursor
        for changed in (
            {"filter_": filter_type(**base, min_faces_total_count=1)},
            {"sort": "mentions_total_count"},
            {"sort_direction": "asc"},
        ):
            kwargs = dict(
                filter_=filter_type(**base),
                sort="faces_total_count",
                cursor=first.cursor,
                limit=1,
            )
            kwargs.update(changed)
            with pytest.raises(ValueError, match="different query"):
                await fetch(request(**kwargs))
    # Aggregate query counts stay constant as response batches grow.
    statements = []

    def capture(*args):
        statements.append(args[2])

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        query = DocumentListRequest(
            limit=1,
            filter_=DocumentListFilter(
                source_id=list(expected_docs), min_annotations_total_count=1
            ),
            sort="faces_manual_count",
        )
        await db.sources.list_documents(query)
        count = len(statements)
        statements.clear()
        await db.sources.list_documents(query.model_copy(update={"limit": 100}))
        assert len(statements) == count
        assert statements[0].count("counted_annotations AS") <= 1
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)


@pytest.mark.asyncio
async def test_count_preview_mutations_preservation_and_interrupted_recovery(
    seed_target,
):
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.services.auth_service import AuthContext

    db, fs, _ = seed_target
    original = await preview.seed_preview(db, fs)
    actor = AuthContext(
        user_id=original.users["reviewer"],
        authentication_method="bearer",
        scopes={"people-gator:annotate"},
    )
    page_id, doc_id = original.pages["count-faces-1"], original.documents["count-faces"]

    async def membership(state, minimum):
        docs = await db.sources.list_documents(
            DocumentListRequest(
                limit=12,
                filter_=DocumentListFilter(
                    source_id=[doc_id], **{f"min_faces_{state}_count": minimum}
                ),
            )
        )
        pages = await db.sources.list_pages(
            PageListRequest(
                limit=12,
                filter_=PageListFilter(
                    source_id=[page_id], **{f"min_faces_{state}_count": minimum}
                ),
            )
        )
        return bool(docs.items), bool(pages.items)

    assert await membership("verified", 2) == (False, False)
    await db.faces.patch(
        original.faces["count-face-0"],
        FacePatchRequest(entity_link_state="verified"),
        actor,
    )
    assert await membership("verified", 2) == (True, True)
    await db.faces.patch(
        original.faces["count-face-0"], FacePatchRequest(entity_id=None), actor
    )
    assert await membership("verified", 2) == (False, False)
    assert await membership("unassigned", 2) == (True, True)
    await db.faces.patch(
        original.faces["count-face-0"],
        FacePatchRequest(
            entity_id=original.entities["table-tereza"], entity_link_state="manual"
        ),
        actor,
    )
    assert await membership("unassigned", 2) == (False, False)
    assert await membership("manual", 2) == (True, True)
    assert await membership("total", 4) == (True, True)
    await db.faces.delete(original.faces["count-face-0"], context=actor)
    assert await membership("total", 4) == (True, False)
    assert await membership("total", 5) == (False, False)
    assert await membership("manual", 2) == (True, False)
    await db.text_mentions.patch(
        original.mentions["count-mention-0"],
        TextMentionPatchRequest(entity_link_state="verified"),
        actor,
    )
    mentions = await db.sources.list_pages(
        PageListRequest(
            limit=12,
            filter_=PageListFilter(
                min_mentions_verified_count=2,
                source_id=[original.pages["count-mentions-1"]],
            ),
        )
    )
    assert len(mentions.items) == 1
    await db.text_mentions.delete(original.mentions["count-mention-0"], context=actor)
    mentions = await db.sources.list_pages(
        PageListRequest(
            limit=12,
            filter_=PageListFilter(
                min_mentions_verified_count=2,
                source_id=[original.pages["count-mentions-1"]],
            ),
        )
    )
    assert not mentions.items
    before = await db.sources.get_document(doc_id)
    await preview.seed_preview(db, fs)
    assert await db.sources.get_document(doc_id) == before
    assert await db.faces.get(original.faces["count-face-0"]) is None
    assert await db.text_mentions.get(original.mentions["count-mention-0"]) is None
    # Lose a checkpoint immediately after writing new evidence; retry must recover
    # the durable synthetic identifier rather than inserting a duplicate.
    raw = await fs.read_bytes(preview.MANIFEST_KEY)
    manifest = json.loads(raw)
    # Existing fixture keys are deliberately removed from the checkpoint only.
    del manifest["faces"]["count-tie-face-0"]
    await fs.write_bytes(preview.MANIFEST_KEY, json.dumps(manifest).encode())
    recovered = await preview.seed_preview(db, fs)
    assert recovered.faces["count-tie-face-0"] == original.faces["count-tie-face-0"]
    assert recovered.filter_examples["annotation-count-documents"]
    doc = await db.sources.get_document(original.documents["count-tie"])
    assert doc.entity_link_stats.faces.total == 4


@pytest.mark.asyncio
async def test_annotation_count_aggregate_plan_with_larger_scope(seed_target):
    """1,000 faces stay one grouped projection and a bounded response."""
    from sqlalchemy import event
    from people_gator_api.schemas.common import BoundingBox, Keypoint
    from people_gator_api.schemas.enums import FaceKeypointType
    from people_gator_api.schemas.sources import DocumentListFilter
    from people_gator_api.services.auth_service import AuthContext

    db, fs, engine = seed_target
    seeded = await preview.seed_preview(db, fs)
    actor = AuthContext(
        user_id=seeded.users["reviewer"],
        authentication_method="bearer",
        scopes={"people-gator:annotate"},
    )
    await db.faces.create_batch(
        [
            FaceCreateRequest(
                source_id=seeded.pages["count-empty-1"],
                confidence=0.9,
                bounding_box=BoundingBox(x=0, y=0, width=50, height=50),
                keypoints=[
                    Keypoint(type=kind, x=10 + i, y=10 + i)
                    for i, kind in enumerate(FaceKeypointType)
                ],
            )
            for _ in range(1000)
        ],
        actor,
    )
    captured = []

    def capture(conn, cursor, statement, params, context, executemany):
        captured.append((statement, params))

    event.listen(engine.sync_engine, "before_cursor_execute", capture)
    try:
        result = await db.sources.list_documents(
            DocumentListRequest(
                limit=1,
                sort="faces_total_count",
                filter_=DocumentListFilter(
                    library=["preview-counts"], min_faces_unassigned_count=1000
                ),
            )
        )
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", capture)
    assert [row.source_id for row in result.items] == [seeded.documents["count-empty"]]
    assert result.items[0].entity_link_stats.faces.total == 1000
    assert len(captured) == 6  # One result query + five bounded summary queries.
    statement, params = captured[0]
    assert "UNION ALL" in statement and "CROSS JOIN" not in statement
    assert statement.count("GROUP BY annotation_scope.owner_id") == 1
    async with engine.connect() as connection:
        raw = await connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, params
        )
        plan = raw.scalar_one()
    if isinstance(plan, str):
        plan = json.loads(plan)
    assert plan[0]["Plan"]["Actual Rows"] == 1
    assert "Aggregate" in json.dumps(plan)
    print(
        "Annotation count plan:",
        json.dumps(
            {
                "annotations_added": 1000,
                "queries": len(captured),
                "execution_ms": plan[0]["Execution Time"],
                "planning_ms": plan[0]["Planning Time"],
            }
        ),
    )
