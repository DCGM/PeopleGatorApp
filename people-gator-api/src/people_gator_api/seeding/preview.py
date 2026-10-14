"""Populate a preview through public repository and filesystem contracts only."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID
from urllib.parse import urlencode

from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field

from people_gator_api.filesystem.contracts import Filesystem
from people_gator_api.media.page_image import page_image_key
from people_gator_api.media.page_layout import page_layout_key
from people_gator_api.media.image_content import image_content_key
from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
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

from .fixtures import DOCUMENTS, MODEL, PAGES, PEOPLE, SECOND_MODEL, ISSUE8_IMAGE_URL, Face
from .media import face_box, face_keypoints, page_image, page_layout

MANIFEST_KEY = "peoplegator_api/preview-seed.json"


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
    manifest = (
        SeedManifest.model_validate_json(raw) if raw is not None else SeedManifest()
    )

    async def checkpoint() -> None:
        await filesystem.write_bytes(
            MANIFEST_KEY, manifest.model_dump_json(indent=2).encode()
        )

    actors: dict[str, AuthContext] = {}
    registered_keys: dict[str, UUID] = {}
    for key, label in (
        ("reviewer", "Preview reviewer"),
        ("importer", "Preview face importer"),
        ("ocr", "Preview OCR linker"),
    ):
        user = await database.users.get_or_create(
            UserCreateRequest(
                display_name=label,
                is_active=True,
                external_subject=key,
                external_issuer="urn:people-gator:preview-seed",
            )
        )
        api_key_id = None
        if key != "reviewer":
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
            user=user,
            api_key_id=api_key_id,
            authentication_method="api_key" if api_key_id else "bearer",
            scopes={"people-gator:ingest", "people-gator:annotate"},
        )
    for model, dimension in ((MODEL, 8), (SECOND_MODEL, 4)):
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
        if await _read_optional(filesystem, image_key) is None:
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
                        confidence=0.97,
                        embeddings=[
                            FaceEmbedding(
                                model_identifier=model,
                                vector=example_vector(face.group, face.key, dim),
                            )
                            for model, dim in ((MODEL, 8), (SECOND_MODEL, 4)) if face.embedded
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
            record = next(
                (
                    item
                    for item in saved_mentions
                    if item.name == person.name and item.context == mention.text
                ),
                None,
            )
            if record is None:
                record = await database.text_mentions.create(
                    TextMentionCreateRequest(
                        name=person.name,
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
    if await _read_optional(filesystem, image_key) is None:
        await filesystem.write_bytes(image_key, page_image(PAGES[0], DOCUMENTS[0]))
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
    statistics_page = await database.sources.get_page(pages["links-2"])
    if statistics_page is None:
        raise ValueError("Link statistics preview page is missing")
    no_ocr_page = await database.sources.get_page(pages["faces-no-ocr-1"])
    if no_ocr_page is None:
        raise ValueError("Faces without OCR preview page is missing")
    return SeedResult(
        entities=active_entities,
        documents=documents,
        pages=pages,
        faces=active_faces,
        mentions=active_mentions,
        users={key: actor.user_id for key, actor in actors.items()},
        api_keys=registered_keys,
        filter_examples={
            "faces-without-ocr": (
                f"/libraries/{no_ocr_page.library}/documents/{no_ocr_page.document_id}"
                f"/pages/{no_ocr_page.page_id}"
            ),
            "link-statistics": (
                f"/libraries/{statistics_page.library}/documents/{statistics_page.document_id}"
                f"/pages/{statistics_page.page_id}#link-statistics"
            ),
            "document-search": "/documents?q=pribehy",
            "document-source-touch": "/documents?library=preview-mzk&touched_by=" + str(actors["reviewer"].user_id),
            "grouped-documents": "/documents?library=preview-mzk",
            "unregistered-scan": "/scans?"
            + urlencode({"library": "preview-mzk", "document": next(
                item.document_id for item in DOCUMENTS if item.key == "scan-only"
            )}),
            "mobile-filters": "/people?"
            + urlencode(
                {
                    "q": "Novak",
                    "assignment": "faces",
                    "document": documents["album"],
                    "touched_by": actors["importer"].user_id,
                    "api_key": registered_keys["importer"],
                }
            ),
        },
    )
