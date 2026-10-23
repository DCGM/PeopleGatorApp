"""Populate a preview through public repository and filesystem contracts only."""

from __future__ import annotations

import hashlib
import json
import math
from uuid import UUID
from urllib.parse import urlencode

from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

from people_gator_api.filesystem.contracts import Filesystem
from people_gator_api.media.page_image import page_image_key
from people_gator_api.media.page_layout import page_layout_key
from people_gator_api.media.image_content import image_content_key
from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityPatchRequest,
    EntityListRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType, EntityLinkState
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FacePatchRequest,
    FaceEmbedding,
    FaceListFilter,
    FaceListRequest,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
    TextMentionListFilter,
    TextMentionListRequest,
)
from people_gator_api.schemas.sources import DocumentCreateRequest, PageCreateRequest, ImageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext

from .fixtures import DOCUMENTS, MODEL, PAGES, PEOPLE, SECOND_MODEL, DISCOVERY_MODEL, DISCOVERY_OTHER_MODEL, ISSUE8_IMAGE_URL, ISSUE8_IMAGE_PAGE, Face
from .media import face_box, face_keypoints, page_image, page_layout, png_image

MANIFEST_KEY = "peoplegator_api/preview-seed.json"
# Upgrade state lives beside the identity manifest. Older seed code rejects
# unknown manifest keys, so a rollback must never find new fields there.
UPGRADES_KEY = "peoplegator_api/preview-seed-upgrades.json"


class ThumbnailUpgrade(BaseModel):
    expected_face_id: UUID | None
    expected_touched_at: AwareDatetime | None
    selected_face_id: UUID
    complete: bool = False


class RecordEditUpgrade(BaseModel):
    """One additive own-record edit, applied only to the unchanged seeded record."""

    expected_touched_at: AwareDatetime | None
    complete: bool = False


class SeedUpgrades(BaseModel):
    # Ignore state written by newer code after a rollback.
    model_config = ConfigDict(extra="ignore")
    thumbnail: dict[str, ThumbnailUpgrade] = Field(default_factory=dict)
    record_edits: dict[str, RecordEditUpgrade] = Field(default_factory=dict)


class SeedManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: dict[str, UUID] = Field(default_factory=dict)
    faces: dict[str, UUID] = Field(default_factory=dict)
    mentions: dict[str, UUID] = Field(default_factory=dict)


class SeedResult(BaseModel):
    entities: dict[str, UUID]
    documents: dict[str, UUID]
    pages: dict[str, UUID]
    faces: dict[str, UUID]
    mentions: dict[str, UUID]
    users: dict[str, UUID]
    api_keys: dict[str, UUID]
    filter_examples: dict[str, str]


def example_vector(group: int, key: str, dimension: int) -> list[float]:
    """Same-person examples cluster together; the other groups remain distinct."""
    digest = hashlib.sha256(key.encode()).digest()
    vector = [
        (1.0 if index == group else 0.0) + digest[index] / 2550
        for index in range(dimension)
    ]
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector]


async def _read_optional(filesystem: Filesystem, key: str) -> bytes | None:
    try:
        return await filesystem.read_bytes(key)
    except FileNotFoundError:
        return None
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            return None
        raise


async def seed_preview(database: Database, filesystem: Filesystem) -> SeedResult:
    """Add missing examples, retaining existing IDs, edits, links and timestamps.

    Run one seeder at a time per database/storage pair. The preview controller
    already serializes deployments. Checkpoints let a failed run resume; stable
    source identities and repository lookups recover a write before its checkpoint.
    """
    if database.api_keys is None:
        raise ValueError("Preview seeding requires the API-key registry (PostgreSQL)")
    raw = await _read_optional(filesystem, MANIFEST_KEY)
    identity = json.loads(raw) if raw is not None else {}
    # Early #35 previews stored portrait upgrade state in the identity manifest.
    legacy_upgrades = identity.pop("thumbnail_upgrades", None)
    manifest = SeedManifest.model_validate(identity)

    raw = await _read_optional(filesystem, UPGRADES_KEY)
    upgrades = (
        SeedUpgrades.model_validate_json(raw) if raw is not None else SeedUpgrades()
    )

    async def checkpoint() -> None:
        await filesystem.write_bytes(
            MANIFEST_KEY, manifest.model_dump_json(indent=2).encode()
        )

    async def checkpoint_upgrades() -> None:
        await filesystem.write_bytes(
            UPGRADES_KEY, upgrades.model_dump_json(indent=2).encode()
        )

    if legacy_upgrades is not None:
        # Save the moved state before removing it from the identity manifest.
        if raw is None:
            upgrades = SeedUpgrades(thumbnail=legacy_upgrades)
            await checkpoint_upgrades()
        await checkpoint()

    actors: dict[str, AuthContext] = {}
    registered_keys: dict[str, UUID] = {}
    for key, label, active in (
        ("reviewer", "Preview reviewer", True),
        ("importer", "Preview face importer", True),
        ("ocr", "Preview OCR linker", True),
        ("curator", "Preview curator", True),
        # Issue #66: an inactive user's earlier bearer writes keep their
        # attribution; get_or_create never reactivates an existing record.
        ("former", "Preview former reviewer", False),
    ):
        user = await database.users.get_or_create(
            UserCreateRequest(
                display_name=label,
                is_active=active,
                external_subject=key,
                external_issuer="urn:people-gator:preview-seed",
            )
        )
        api_key_id = None
        if key not in {"reviewer", "former"}:
            registered = await database.api_keys.get_or_create(
                APIKeyCreateRequest(
                    identifier="preview-seed-" + key,
                    display_name=label,
                    user_id=user.user_id,
                )
            )
            api_key_id = registered.api_key_id
            registered_keys[key] = api_key_id
        actors[key] = AuthContext(
            user_id=user.user_id,
            api_key_id=api_key_id,
            authentication_method="api_key" if api_key_id else "bearer",
            scopes={"people-gator:ingest", "people-gator:annotate"},
        )
    for model, dimension in ((MODEL, 8), (SECOND_MODEL, 4), (DISCOVERY_MODEL, 8), (DISCOVERY_OTHER_MODEL, 4)):
        await database.face_models.register(
            FaceModelRegisterRequest(model_stub=model, embedding_dim=dimension)
        )

    # Recovery lookup for a repository write that preceded a failed checkpoint.
    # Match only our separate seed owner, never another user's similarly named person.
    existing: list[EntityResponse] = []
    cursor = None
    while True:
        result = await database.entities.list(
            EntityListRequest(limit=100, cursor=cursor)
        )
        existing.extend(
            item for item in result.items if item.user_id == actors["reviewer"].user_id
        )
        cursor = result.cursor
        if cursor is None:
            break
    active_entities: dict[str, UUID] = {}
    active_faces: dict[str, UUID] = {}
    active_mentions: dict[str, UUID] = {}
    for person in PEOPLE:
        entity_id = manifest.entities.get(person.key)
        if entity_id is not None:
            # Keep checkpointed IDs as tombstones after deliberate deletes/merges.
            if await database.entities.get(entity_id) is not None:
                active_entities[person.key] = entity_id
            continue
        entity = next((item for item in existing if item.name == person.name), None)
        if entity is None:
            entity = await database.entities.create(
                EntityCreateRequest(
                    entity_type=EntityType.person,
                    name=person.name,
                    aliases=list(person.aliases),
                    short_description=person.description,
                    description=person.description
                    + " This record belongs to the synthetic preview dataset.",
                ),
                actors["reviewer"],
            )
            existing.append(entity)
        manifest.entities[person.key] = entity.entity_id
        active_entities[person.key] = entity.entity_id
        await checkpoint()

    documents: dict[str, UUID] = {}
    pages: dict[str, UUID] = {}
    for document in DOCUMENTS:
        if not document.registered:
            continue
        source, _ = await database.sources.get_or_create_document(
            DocumentCreateRequest(
                library=document.library,
                document_id=document.document_id,
                name=document.title if document.named else None,
            )
        )
        documents[document.key] = source.source_id
    people = {person.key: person for person in PEOPLE}
    for page in PAGES:
        document = next(item for item in DOCUMENTS if item.key == page.document)
        source, _ = await database.sources.get_or_create_page(
            PageCreateRequest(
                library=document.library,
                document_id=document.document_id,
                page_id=page.page_id,
            )
        )
        pages[page.key] = source.source_id
        image_key = page_image_key(document.library, document.document_id, page.page_id)
        if page.has_image and await _read_optional(filesystem, image_key) is None:
            await filesystem.write_bytes(image_key, page_image(page, document))
        layout_key = page_layout_key(
            document.library, document.document_id, page.page_id
        )
        if page.has_layout and await _read_optional(filesystem, layout_key) is None:
            await filesystem.write_bytes(
                layout_key, page_layout(page).model_dump_json().encode()
            )

        saved_faces = (
            await database.faces.list(
                FaceListRequest(
                    limit=100,
                    filter_=FaceListFilter(source_id=[source.source_id]),
                )
            )
        ).items
        for face in page.faces:
            detection_id = manifest.faces.get(face.key)
            if detection_id is not None:
                if await database.faces.get(detection_id) is not None:
                    active_faces[face.key] = detection_id
                continue
            if face.person is not None and face.person not in active_entities:
                continue
            identifier = "preview-seed/" + face.key
            detection = next(
                (item for item in saved_faces if item.identifier == identifier), None
            )
            if detection is None:
                fields = (
                    {"entity_id": manifest.entities[face.person], "entity_link_state": EntityLinkState.manual if face.state == "manual" else EntityLinkState.automatic} if face.person else {}
                )
                detection = await database.faces.create(
                    FaceCreateRequest(
                        identifier=identifier,
                        source_id=source.source_id,
                        bounding_box=face_box(face),
                        keypoints=face_keypoints(face),
                        confidence=face.confidence,
                        embeddings=[
                            FaceEmbedding(
                                model_identifier=model,
                                vector=[0.0] * dim if face.zero_vector else example_vector(face.group, face.key, dim),
                            )
                            for model, dim in ((MODEL, 8), (SECOND_MODEL, 4), (DISCOVERY_MODEL, 8), (DISCOVERY_OTHER_MODEL, 4)) if face.embedded and model in face.models
                        ],
                        **fields,
                    ),
                    actors[people[face.person].actor]
                    if face.person
                    else actors["importer"],
                )
            if face.state == "verified" and detection.entity_id == active_entities.get(face.person) and detection.entity_link_state == EntityLinkState.automatic:
                detection = await database.faces.patch(detection.detection_id, FacePatchRequest(entity_link_state=EntityLinkState.verified), actors["reviewer"])
            manifest.faces[face.key] = detection.detection_id
            active_faces[face.key] = detection.detection_id
            await checkpoint()

        saved_mentions = (
            await database.text_mentions.list(
                TextMentionListRequest(
                    limit=100,
                    filter_=TextMentionListFilter(source_id=[source.source_id]),
                )
            )
        ).items
        for mention in page.mentions:
            mention_id = manifest.mentions.get(mention.key)
            if mention_id is not None:
                if await database.text_mentions.get(mention_id) is not None:
                    active_mentions[mention.key] = mention_id
                continue
            if mention.person not in active_entities:
                continue
            person = people[mention.person]
            recorded = mention.recorded or person.name
            record = next(
                (
                    item
                    for item in saved_mentions
                    if item.name == recorded and item.context == mention.text
                ),
                None,
            )
            if record is None:
                record = await database.text_mentions.create(
                    TextMentionCreateRequest(
                        name=recorded,
                        entity_link_state=EntityLinkState.manual if mention.state == "manual" else EntityLinkState.automatic,
                        context=mention.text,
                        entity_id=manifest.entities[person.key],
                        source_id=source.source_id,
                    ),
                    actors[person.actor],
                )
            if record.entity_id == active_entities.get(person.key) and record.entity_link_state == EntityLinkState.automatic:
                if mention.state == "verified":
                    record = await database.text_mentions.patch(record.mention_id, TextMentionPatchRequest(entity_link_state=EntityLinkState.verified), actors["reviewer"])
                elif mention.state is None:
                    record = await database.text_mentions.patch(record.mention_id, TextMentionPatchRequest(entity_id=None), actors["reviewer"])
            manifest.mentions[mention.key] = record.mention_id
            active_mentions[mention.key] = record.mention_id
            await checkpoint()
    # Standalone image uses the same generic source touch as document pages.
    image, _ = await database.sources.get_or_create_image(ImageCreateRequest(url=ISSUE8_IMAGE_URL))
    image_key = image_content_key(ISSUE8_IMAGE_URL)
    stored_image = await _read_optional(filesystem, image_key)
    image_document = next(item for item in DOCUMENTS if item.key == ISSUE8_IMAGE_PAGE.document)
    # Narrow upgrade for the exact JPEG bytes written by the initial issue #8
    # fixture. Preserve any reviewed/replaced media and all source identities.
    legacy_images = {page_image(PAGES[0], item) for item in DOCUMENTS if item.key in {"issue8-search", "issue8-direct"}}
    if stored_image is None or stored_image in legacy_images:
        await filesystem.write_bytes(image_key, png_image(ISSUE8_IMAGE_PAGE, image_document))
    key = "issue8-image-face"
    if key not in manifest.faces:
        existing_faces = (await database.faces.list(FaceListRequest(
            limit=100, filter_=FaceListFilter(source_id=[image.source_id]),
        ))).items
        detection = next((face for face in existing_faces if face.identifier == "preview-seed/" + key), None)
        if detection is None:
            face = Face(key, None, 0, 2)
            detection = await database.faces.create(FaceCreateRequest(
                identifier="preview-seed/" + key, source_id=image.source_id,
                bounding_box=face_box(face), keypoints=face_keypoints(face), confidence=0.97,
            ), actors["importer"])
        manifest.faces[key] = detection.detection_id
        await checkpoint()
    if await database.faces.get(manifest.faces[key]) is not None:
        active_faces[key] = manifest.faces[key]
    # Direct document evidence is searchable even without a matching page.
    key = "issue8-direct-mention"
    if key not in manifest.mentions and "link-emil" in active_entities:
        source_id = documents["issue8-direct"]
        records = (await database.text_mentions.list(TextMentionListRequest(
            limit=100, filter_=TextMentionListFilter(source_id=[source_id]),
        ))).items
        context = "Emil Review catalogued the direct annotation ledger."
        record = next((item for item in records if item.context == context), None)
        if record is None:
            record = await database.text_mentions.create(TextMentionCreateRequest(
                name="Emil Review", context=context, entity_id=active_entities["link-emil"],
                entity_link_state=EntityLinkState.manual, source_id=source_id,
            ), actors["reviewer"])
        manifest.mentions[key] = record.mention_id
        await checkpoint()
    if key in manifest.mentions and await database.text_mentions.get(manifest.mentions[key]) is not None:
        active_mentions[key] = manifest.mentions[key]
    # Explicit, checkpointed additive upgrade for #35. Use existing synthetic
    # linked media; preserve manual choices and every choice after this upgrade.
    # Record the precondition BEFORE writing, so an interrupted checkpoint cannot
    # undo a subsequent review edit or turn a reviewer reset back into manual.
    upgrade_key = "person-portrait-v1"
    person_id = active_entities.get("provenance-review")
    person = await database.entities.get(person_id) if person_id else None
    if person is not None:
        upgrade = upgrades.thumbnail.get(upgrade_key)
        if upgrade is None:
            choices = (await database.faces.list(FaceListRequest(
                filter_=FaceListFilter(entity_id=[person_id]), limit=100,
            ))).items
            seeded_ids = {active_faces.get(key) for key in (
                "provenance-auto", "provenance-authority", "provenance-manual", "provenance-unknown",
            )}
            candidates = sorted(face.detection_id for face in choices if face.detection_id in seeded_ids)
            if len(candidates) >= 2:
                upgrade = ThumbnailUpgrade(
                    expected_face_id=person.thumbnail_face_id,
                    expected_touched_at=person.last_touched_at,
                    selected_face_id=candidates[-1],
                    complete=person.thumbnail_mode == "manual",
                )
                upgrades.thumbnail[upgrade_key] = upgrade
                await checkpoint_upgrades()
        if upgrade is not None and not upgrade.complete:
            candidate = await database.faces.get(upgrade.selected_face_id)
            if (person.thumbnail_mode == "automatic"
                    and person.thumbnail_face_id == upgrade.expected_face_id
                    and person.last_touched_at == upgrade.expected_touched_at
                    and candidate is not None and candidate.entity_id == person_id):
                await database.entities.patch(person_id, EntityPatchRequest(
                    thumbnail_face_id=upgrade.selected_face_id,
                ), actors["reviewer"])
            upgrade.complete = True
            await checkpoint_upgrades()
    # Explicit additive upgrade for #52: the curator edits Hana's own record
    # after the reviewer's face link, so her own latest modifier differs from
    # her linked face's. Record the precondition first; never overwrite a later
    # review edit, and never repeat the edit after an interrupted checkpoint.
    upgrade_key = "shared-filters-own-edit-v1"
    person_id = active_entities.get("shared-hana")
    person = await database.entities.get(person_id) if person_id else None
    if person is not None:
        edit = upgrades.record_edits.get(upgrade_key)
        if edit is None:
            edit = RecordEditUpgrade(expected_touched_at=person.last_touched_at)
            upgrades.record_edits[upgrade_key] = edit
            await checkpoint_upgrades()
        if not edit.complete:
            if (person.last_touched_at == edit.expected_touched_at
                    and person.last_touched_by_user_id == actors["reviewer"].user_id):
                curator = actors["curator"]
                await database.entities.patch(person_id, EntityPatchRequest(
                    short_description="Curated after the reviewer linked her face.",
                ), AuthContext(
                    user_id=curator.user_id, api_key_id=None,
                    authentication_method="bearer", scopes=curator.scopes,
                ))
            edit.complete = True
            await checkpoint_upgrades()
    statistics_page = await database.sources.get_page(pages["links-2"])
    if statistics_page is None:
        raise ValueError("Link statistics preview page is missing")
    toolbar_union_page = await database.sources.get_page(pages["links-1"])
    if toolbar_union_page is None:
        raise ValueError("Scan toolbar union preview page is missing")
    no_ocr_page = await database.sources.get_page(pages["faces-no-ocr-1"])
    if no_ocr_page is None:
        raise ValueError("Faces without OCR preview page is missing")
    upload_page = await database.sources.get_page(pages["media-upload-1"])
    if upload_page is None:
        raise ValueError("Media upload preview page is missing")
    activity_page = next(item for item in PAGES if item.key == "provenance-a-1")
    gallery_document = next(item for item in DOCUMENTS if item.key == "page-gallery")
    focus_document = next(item for item in DOCUMENTS if item.key == "focus")
    focus_path = (
        f"/libraries/{focus_document.library}/documents/{focus_document.document_id}"
        f"/pages/{next(item.page_id for item in PAGES if item.key == 'focus-1')}"
    )
    search_document = next(item for item in DOCUMENTS if item.key == "issue8-search")
    sorting_document = next(item for item in DOCUMENTS if item.key == "sorting-ledger")
    sorting_person = manifest.entities.get("sorting")
    activity_document = next(item for item in DOCUMENTS if item.key == activity_page.document)
    discovery_page = next(item for item in PAGES if item.key == "discovery-1")
    discovery_document = next(item for item in DOCUMENTS if item.key == discovery_page.document)
    return SeedResult(
        entities=active_entities,
        documents=documents,
        pages=pages,
        faces=active_faces,
        mentions=active_mentions,
        users={key: actor.user_id for key, actor in actors.items()},
        api_keys=registered_keys,
        filter_examples={
            # Workspace criteria stay in navigation; the scan panel uses page membership or global search.
            "global-discovery-scan": (
                f"/libraries/{discovery_document.library}/documents/{discovery_document.document_id}"
                f"/pages/{discovery_page.page_id}?" + urlencode({
                    "candidate_mode": "face", "person": active_faces.get("discovery-reference-0", ""),
                    "library": "preview-mzk", "document": documents["discovery"],
                    "page": pages["discovery-1"],
                })
            ),
            "global-discovery-scan-excluded": (
                f"/libraries/{discovery_document.library}/documents/{discovery_document.document_id}"
                f"/pages/{discovery_page.page_id}?" + urlencode({
                    "candidate_mode": "face", "person": active_faces.get("discovery-reference-0", ""),
                    "library": "preview-mzk", "touched_by": actors["reviewer"].user_id,
                })
            ),
            **{
                key: (
                    f"/libraries/{discovery_document.library}/documents/{discovery_document.document_id}"
                    f"/pages/{discovery_page.page_id}?" + urlencode({
                        "candidate_mode": "page", "library": "preview-mzk",
                        "link_state": "verified", "touched_by": actors["reviewer"].user_id,
                        "api_key": registered_keys["ocr"], **extra,
                    })
                )
                for key, extra in (
                    ("scan-page-entities", {}),
                    ("scan-global-text", {"candidate_text": "Orion"}),
                )
            },
            "global-discovery": f"/people/{manifest.entities['discovery']}?" + urlencode({
                "tab": "discover", "discovery_model": DISCOVERY_MODEL,
                "discovery_annotations": "faces", "library": "preview-mzk",
                "document": documents["discovery"], "page": pages["discovery-1"],
                "link_state": "verified", "touched_by": actors["reviewer"].user_id,
                "api_key": registered_keys["ocr"],
            }),

            **{
                f"{key}-crop": f"/api/v1/faces/{active_faces[key]}/aligned_crop?max_width=256"
                for key in ("alignment-coincident", "alignment-valid") if key in active_faces
            },
            "pagination-people": "/people?q=Pagination&sort=name",
            "pagination-scans": "/scans?library=preview-pagination&q=Pagination",
            "pagination-browse-people": "/people?library=preview-pagination&sort=name",
            "pagination-browse-scans": "/scans?library=preview-pagination&sort=page_id",
            "pagination-documents": "/documents?library=preview-pagination&q=Pagination&sort=name",
            "pagination-scoped-scans": "/scans?" + urlencode({"document": documents["page-gallery"]}),
            **({"entity-discovery": f"/people/{manifest.entities['discovery']}?" + urlencode({
                "tab": "discover", "discovery_model": DISCOVERY_MODEL,
            }), "entity-discovery-identifier": f"/people/{manifest.entities['discovery']}?" + urlencode({
                "tab": "discover", "discovery_annotations": "none",
                "discovery_text": "preview-seed/discovery-unassigned",
            })} if 'discovery' in manifest.entities else {}),
            # Root entry demonstrates the Documents landing view with the existing
            # linked album/media. These entry points require no persisted upgrade.
            "default-documents": "/",
            "default-documents-scans": "/scans?" + urlencode({"document": documents["album"]}),
            # Select one existing linked evidence card, then Use as portrait in
            # the compact bottom bar. Select the marked portrait to reset.
            "person-portrait-selection": f"/people/{manifest.entities['provenance-review']}",

            # Compare the standard state text colors without state backgrounds.
            "linked-face-states": f"/people/{manifest.entities['provenance-review']}?" + urlencode({
                "link_state": ["automatic", "manual", "verified"],
            }, doseq=True),
            # Ada Review's sidebar shows automatic/verified counts beside a zero
            # manual count and her recorded last change (#43).
            "person-last-change": f"/people/{manifest.entities['link-ada']}",
            "document-pages-without-annotations": "/documents?" + urlencode({
                "q": "Příběhy archivářů",
            }),
            # Person faces last changed by the importer's key: the same shared
            # user/key criteria as Documents/People, applied to each face (#52).
            "annotation-editor-filters": f"/people/{manifest.entities['provenance-review']}?" + urlencode({
                "touched_by": actors["importer"].user_id,
                "api_key": registered_keys["importer"],
            }),
            # Open Irena's scan, then search for Ada as an assignment candidate
            # outside that page. Opening a result must not invent evidence scope.
            "scan-assignment-search": "/scans?" + urlencode({"document": documents[activity_document.key]}),
            # Follow Irena into a profile: the library scope keeps only her
            # preview-mzk faces. Edit it, then use the People breadcrumb.
            "shared-filter-navigation": "/people?" + urlencode({
                "q": "Irena",
                "library": "preview-mzk",
            }),
            # Issue #52: one configuration, each view's own latest change.
            # Documents → People keeps the curator selection: the ledger
            # document, Ivo (curator's key) and Hana (curator's own edit).
            # Issue #66: Olga's mention stays attributed to a now-inactive
            # reviewer, who is still offered as an editor filter.
            "deactivated-reviewer": "/people?" + urlencode({
                "touched_by": actors["former"].user_id,
            }),
            "shared-filters-documents": "/documents?" + urlencode({
                "touched_by": actors["curator"].user_id,
            }),
            "shared-filters-people": "/people?" + urlencode({
                "touched_by": actors["curator"].user_id,
            }),
            # Adding the curator's key leaves Ivo; Hana's edit used no key.
            "shared-filters-api-key": "/people?" + urlencode({
                "touched_by": actors["curator"].user_id,
                "api_key": registered_keys["curator"],
            }),
            # Hana's profile under the curator selection: her own record matches,
            # but her face was last changed by the reviewer, so it is filtered out.
            "shared-filters-person-faces": f"/people/{manifest.entities['shared-hana']}?" + urlencode({
                "touched_by": actors["curator"].user_id,
            }),
            # Document scope by internal UUID; the same archive ID in preview-nlk
            # has no links and never contributes results.
            "shared-filters-scope": "/people?" + urlencode({"document": documents["shared-ledger"]}),
            # Strict page scope: Scans selects this page; People finds Hana
            # through her face, while Documents never includes the parent ledger.
            "shared-filters-page": "/scans?" + urlencode({"page": pages["shared-ledger-1"]}),
            "shared-filters-page-people": "/people?" + urlencode({"page": pages["shared-ledger-1"]}),
            # Presentation examples reuse linked synthetic records and media.
            # Adding entry points never rewrites reviewer edits or checkpoints.
            # Mixed-state faces exercise green-outline Verify/red-outline Unassign;
            # this entry point changes no persisted evidence on retained previews.
            # Compare Faces/Discover library + document rows and plain editor names.
            # Seeded importer/reviewer labels remain usable before the user tab exists.
            "person-face-style-comparison": f"/people/{manifest.entities['provenance-review']}?tab=discover",
            "person-face-review": f"/people/{manifest.entities['provenance-review']}",
            "person-evidence-cards": f"/people/{manifest.entities['provenance-review']}?" + urlencode({
                "origin_matched_face": manifest.faces["provenance-authority"],
            }),
            "page-statistics": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}?panel=statistics"
            ),
            "page-activity": (
                f"/libraries/{activity_document.library}/documents/{activity_document.document_id}"
                f"/pages/{activity_page.page_id}?panel=activity"
            ),
            # Reuse the maintained review records and local media: page 1 has
            # automatic/manual evidence; page 2 has verified/unassigned evidence.
            # These links add a toolbar scenario without rewriting reviewed data.
            "scan-toolbar": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}"
            ),
            "scan-toolbar-union": (
                f"/libraries/{toolbar_union_page.library}/documents/{toolbar_union_page.document_id}"
                f"/pages/{toolbar_union_page.page_id}?"
                + urlencode({"page_link_state": ["automatic", "manual"]}, doseq=True)
            ),
            "scan-toolbar-assigned": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}?"
                + urlencode({"page_link_state": ["automatic", "manual", "verified"]}, doseq=True)
            ),
            "viewport-focus": focus_path,
            # Reuse Ada's two linked OCR lines; no persisted fixtures need changing.
            "person-mention-highlights": (
                focus_path + "?" + urlencode({"selectedPerson": manifest.entities["ada"]})
            ),
            # Ada Review's verified mention spans two OCR lines; Emil Review's
            # lines on the same page belong to another (or no) identity.
            "person-mention-highlights-multiline": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}?"
                + urlencode({"selectedPerson": manifest.entities["link-ada"]})
            ),
            # Fourteen evidence-free pages exceed one 12-page gallery batch and
            # page 9 has no media. List order follows internal source keys, so
            # any page may need a further batch; the gallery loads until found.
            "document-page-gallery": (
                f"/libraries/{gallery_document.library}/documents/{gallery_document.document_id}"
                f"/pages/{next(item.page_id for item in PAGES if item.key == 'page-gallery-13')}"
            ),
            # Shared filters narrow the scan's faces/mentions, never its page
            # gallery: the importer's latest changes cover 3 of 6 pages.
            "document-page-gallery-filtered": (
                f"/libraries/{search_document.library}/documents/{search_document.document_id}"
                f"/pages/{next(item.page_id for item in PAGES if item.key == 'issue8-untouched')}?"
                + urlencode({"touched_by": actors["importer"].user_id})
            ),
            "media-upload": (
                f"/libraries/{upload_page.library}/documents/{upload_page.document_id}"
                f"/pages/{upload_page.page_id}"
            ),
            "faces-without-ocr": (
                f"/libraries/{no_ocr_page.library}/documents/{no_ocr_page.document_id}"
                f"/pages/{no_ocr_page.page_id}"
            ),
            "link-statistics": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}#link-statistics"
            ),
            # Issue #33: every list sorts its complete result set before paging.
            "sorting-documents": "/documents?sort=page_count",
            "sorting-document-names": "/documents?" + urlencode({"q": "radkova", "sort": "name"}),
            "sorting-people": "/people?sort=last_touched_at",
            "sorting-scans": "/scans?" + urlencode({
                "document": documents[sorting_document.key],
                "sort": "page_id", "dir": "desc",
            }),
            **({
                "sorting-faces": f"/people/{sorting_person}?" + urlencode({
                    "face_sort": "confidence", "face_dir": "desc",
                }),
                "sorting-mention-groups": f"/people/{sorting_person}?" + urlencode({
                    "tab": "mentions", "mention_view": "groups", "group_sort": "count",
                }),
                "sorting-similar-faces": f"/people/{sorting_person}?" + urlencode({
                    "tab": "discover", "similar_sort": "confidence",
                }),
            } if sorting_person else {}),
            "document-search": "/documents?q=pribehy",
            "document-preview-remainder": "/documents?q=pribehy&library=preview-mzk",
            "compact-document-filters": "/documents?" + urlencode({
                "q": "pribehy", "library": ["preview-mzk", "preview-nlk"],
                "link_state": ["automatic", "verified"], "unassigned": "no",
                "touched_by": actors["reviewer"].user_id,
            }, doseq=True),
            "outline-filter-badges": "/documents?" + urlencode({
                "q": next(str(item.document_id) for item in DOCUMENTS if item.key == "issue8-search"),
                "library": ["preview-mzk", "preview-nlk"],
                "link_state": ["automatic", "verified"], "unassigned": "no",
            }, doseq=True),
            "rounded-filter-removal": "/documents?" + urlencode({
                "q": "pribehy", "library": "preview-mzk",
                "link_state": ["automatic", "verified"], "unassigned": "no",
            }, doseq=True),
            "document-source-touch": "/documents?library=preview-mzk&touched_by=" + str(actors["reviewer"].user_id),
            "grouped-documents": "/documents?library=preview-mzk",
            "unregistered-scan": "/scans?"
            + urlencode({"library": "preview-mzk", "archive_document": next(
                item.document_id for item in DOCUMENTS if item.key == "scan-only"
            )}),
            "mobile-filters": "/people?"
            + urlencode(
                {
                    "q": "Novak",
                    "link_state": "automatic",
                    "assignment": "faces",
                    "document": documents["album"],
                    "touched_by": actors["importer"].user_id,
                    "api_key": registered_keys["importer"],
                }
            ),
        },
    )
