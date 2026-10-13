"""Opt-in contract checks against a disposable Weaviate server."""

import os
import uuid
import pytest
import weaviate
from people_gator_api.persistence.weaviate import weaviate_database
from people_gator_api.persistence.weaviate.client import ensure_collections
from people_gator_api.schemas.common import GenericActor
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListFilter,
    EntityListRequest,
)
from people_gator_api.schemas.enums import EntityType, EntityLinkState, FaceKeypointType
from people_gator_api.schemas.faces import (
    FaceCreateRequest,
    FacePatchRequest,
    BoundingBox,
    Keypoint,
)
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchRequest,
)
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    PageCreateRequest,
    DocumentListFilter,
    DocumentListRequest,
)


@pytest.mark.skipif(
    not os.getenv("PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT"),
    reason="requires disposable Weaviate",
)
@pytest.mark.asyncio
async def test_weaviate_link_contract_and_additive_upgrade():
    client = weaviate.use_async_with_custom(
        http_host="localhost",
        http_port=int(os.environ["PEOPLE_GATOR_WEAVIATE_TEST_HTTP_PORT"]),
        http_secure=False,
        grpc_host="localhost",
        grpc_port=int(os.environ["PEOPLE_GATOR_WEAVIATE_TEST_GRPC_PORT"]),
        grpc_secure=False,
    )
    await client.connect()
    try:
        await ensure_collections(client)
        db = weaviate_database(client)
        marker = uuid.uuid4().hex
        user = await db.users.get_or_create(
            UserCreateRequest(
                display_name="Synthetic reviewer",
                external_issuer="issue6-test",
                external_subject=marker,
                is_active=True,
            )
        )
        actor = GenericActor(user_id=user.user_id)
        ada, emil = await db.entities.create_batch(
            [
                EntityCreateRequest(name=name + marker, entity_type=EntityType.person)
                for name in ("Ada", "Emil")
            ],
            actor,
        )
        doc, _ = await db.sources.get_or_create_document(
            DocumentCreateRequest(
                library="issue6", document_id=uuid.uuid4(), name="Review"
            )
        )
        page, _ = await db.sources.get_or_create_page(
            PageCreateRequest(
                library=doc.library, document_id=doc.document_id, page_id=uuid.uuid4()
            )
        )
        face = await db.faces.create(
            FaceCreateRequest(
                source_id=page.source_id,
                entity_id=ada.entity_id,
                bounding_box=BoundingBox(x=0, y=0, width=20, height=30),
                keypoints=[Keypoint(type=kind, x=2, y=2) for kind in FaceKeypointType],
                confidence=0.9,
            ),
            actor,
        )
        mention = await db.text_mentions.create(
            TextMentionCreateRequest(
                name="Ada",
                context="Caption",
                source_id=page.source_id,
                entity_id=ada.entity_id,
            ),
            actor,
        )
        for repo, record_id, patch in (
            (db.faces, face.detection_id, FacePatchRequest),
            (db.text_mentions, mention.mention_id, TextMentionPatchRequest),
        ):
            assert (
                await repo.get(record_id)
            ).entity_link_state == EntityLinkState.automatic
            verified = await repo.patch(
                record_id, patch(entity_link_state="verified"), actor
            )
            stored = await repo.get(record_id)
            assert stored.entity_link_verified_by_user_id == actor.user_id
            assert stored.entity_link_verified_at == verified.entity_link_verified_at
            repeated = await repo.patch(
                record_id, patch(entity_link_state="verified"), actor
            )
            assert repeated.entity_link_verified_at == verified.entity_link_verified_at
            with pytest.raises(ValueError):
                await repo.patch(
                    record_id,
                    patch(entity_id=emil.entity_id, entity_link_state="verified"),
                    actor,
                )
            assert (await repo.get(record_id)).entity_id == ada.entity_id
        stats = (await db.sources.get_document(doc.source_id)).entity_link_stats
        assert (
            stats.faces.verified
            == stats.faces.total
            == stats.mentions.verified
            == stats.mentions.total
            == 1
        )
        entities = await db.entities.list(
            EntityListRequest(
                limit=10,
                filter_=EntityListFilter(
                    document_source_id=[doc.source_id], entity_link_state=["verified"]
                ),
            )
        )
        assert [item.entity_id for item in entities.items] == [ada.entity_id]
        docs = await db.sources.list_documents(
            DocumentListRequest(
                limit=100,
                filter_=DocumentListFilter(
                    entity_id=[ada.entity_id], entity_link_state=["verified"]
                ),
            )
        )
        assert doc.source_id in {item.source_id for item in docs.items}
        moved = await db.text_mentions.patch(
            mention.mention_id, TextMentionPatchRequest(entity_id=emil.entity_id), actor
        )
        assert (
            moved.entity_link_state == EntityLinkState.manual
            and moved.entity_link_verified_at is None
        )
        assert (
            await db.text_mentions.get(mention.mention_id)
        ).entity_id == emil.entity_id
        merged = await db.entities.merge(ada.entity_id, emil.entity_id, context=actor)
        assert merged.text_mentions_reassigned == 1
        assert (
            await db.faces.get(face.detection_id)
        ).entity_link_state == EntityLinkState.verified
        assert (
            await db.text_mentions.get(mention.mention_id)
        ).entity_link_state == EntityLinkState.manual
        before_upgrade = await db.faces.get(face.detection_id)
        legacy_id = uuid.uuid4()
        stored = await client.collections.get("Face").query.fetch_object_by_id(
            face.detection_id
        )
        await client.collections.get("Face").data.insert(
            uuid=legacy_id,
            properties={
                key: value
                for key, value in stored.properties.items()
                if not key.startswith("entity_link_")
                and key not in ("linked_entity_id", "annotation_source_id")
            },
            references={
                "entity": ada.entity_id,
                "source": page.source_id,
                "user": user.user_id,
            },
        )
        await ensure_collections(client)
        assert (
            await db.faces.get(face.detection_id)
        ).entity_link_verified_at == before_upgrade.entity_link_verified_at
        assert (
            await db.faces.get(legacy_id)
        ).entity_link_state == EntityLinkState.automatic
        await db.entities.delete_batch([ada.entity_id])
        for repo, record_id in (
            (db.faces, face.detection_id),
            (db.text_mentions, mention.mention_id),
        ):
            stored = await repo.get(record_id)
            assert (
                stored.entity_id
                is stored.entity_link_state
                is stored.entity_link_verified_at
                is None
            )
        stats = (await db.sources.get_document(doc.source_id)).entity_link_stats
        assert stats.faces.unassigned == 2 and stats.mentions.unassigned == 1
    finally:
        await client.close()
