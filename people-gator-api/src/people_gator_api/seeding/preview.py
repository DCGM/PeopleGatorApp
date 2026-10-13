"""Populate a preview through public repository and filesystem contracts only."""

from __future__ import annotations

import hashlib
import math
from uuid import UUID

from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field

from people_gator_api.filesystem.contracts import Filesystem
from people_gator_api.media.page_image import page_image_key
from people_gator_api.media.page_layout import page_layout_key
from people_gator_api.persistence.contracts import Database
from people_gator_api.schemas.api_keys import APIKeyCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListRequest,
    EntityResponse,
)
from people_gator_api.schemas.enums import EntityType
from people_gator_api.schemas.face_models import FaceModelRegisterRequest
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FaceEmbedding,
    FaceListFilter,
    FaceListRequest,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionListFilter,
    TextMentionListRequest,
)
from people_gator_api.schemas.sources import DocumentCreateRequest, PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext

from .fixtures import DOCUMENTS, MODEL, PAGES, PEOPLE, SECOND_MODEL
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
        source, _ = await database.sources.get_or_create_document(
            DocumentCreateRequest(
                library=document.library,
                document_id=document.document_id,
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
        if await _read_optional(filesystem, layout_key) is None:
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
                    {"entity_id": manifest.entities[face.person]} if face.person else {}
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
                            for model, dim in ((MODEL, 8), (SECOND_MODEL, 4))
                        ],
                        **fields,
                    ),
                    actors[people[face.person].actor]
                    if face.person
                    else actors["importer"],
                )
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
                        context=mention.text,
                        entity_id=manifest.entities[person.key],
                        source_id=source.source_id,
                    ),
                    actors[person.actor],
                )
            manifest.mentions[mention.key] = record.mention_id
            active_mentions[mention.key] = record.mention_id
            await checkpoint()
    return SeedResult(
        entities=active_entities,
        documents=documents,
        pages=pages,
        faces=active_faces,
        mentions=active_mentions,
        users={key: actor.user_id for key, actor in actors.items()},
        api_keys=registered_keys,
    )
