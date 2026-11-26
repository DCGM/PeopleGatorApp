"""Issue #176: unlinked mentions from the scan and text edits that keep the link."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.media.text_mention_spans import (
    _fetch_text_mentions,  # pyright: ignore[reportPrivateUsage]
    _match_text_mention_spans,  # pyright: ignore[reportPrivateUsage]
)
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.schemas.entities import EntityCreateRequest
from people_gator_api.schemas.enums import EntityLinkState, EntityType
from people_gator_api.schemas.mentions import (
    TextMentionCreateRequest,
    TextMentionPatchBatchItem,
    TextMentionPatchRequest,
)
from people_gator_api.schemas.pero import PageLayoutModel, RegionLayoutModel, TextLineModel
from people_gator_api.schemas.sources import DocumentCreateRequest, PageCreateRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext


async def _actor(db, name):
    user = await db.users.get_or_create(UserCreateRequest(
        display_name=name, is_active=True, external_subject=name, external_issuer="issue176",
    ))
    return AuthContext(user_id=user.user_id, api_key_id=None, authentication_method="bearer", scopes=set())


async def _page(db, actor):
    document = uuid.uuid4()
    await db.sources.get_or_create_document(
        DocumentCreateRequest(library="issue176", document_id=document), context=actor,
    )
    page, _ = await db.sources.get_or_create_page(
        PageCreateRequest(library="issue176", document_id=document, page_id=uuid.uuid4(), page_number=1),
        context=actor,
    )
    return page


def _layout(*texts: str) -> PageLayoutModel:
    return PageLayoutModel(
        id="page", page_size=(100, 100), reading_order={"r": 0},
        regions=[RegionLayoutModel(id="r", polygon=[], lines=[
            TextLineModel(id=f"l{index}", baseline=[], polygon=[], heights=[], transcription=text, index=index)
            for index, text in enumerate(texts)
        ])],
    )


@pytest.mark.asyncio
async def test_unlinked_mentions_are_created_singly_and_in_batches(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor = await _actor(db, "Annotator")
        page = await _page(db, actor)

        single = await db.text_mentions.create(
            TextMentionCreateRequest(name="Jan Novak", context="Jan Novak signed.", source_id=page.source_id),
            actor,
        )
        batch = await db.text_mentions.create_batch(
            [TextMentionCreateRequest(name="Eva", source_id=page.source_id)], actor,
        )

        for mention in (single, *batch):
            stored = await db.text_mentions.get(mention.mention_id)
            assert stored is not None
            assert stored.entity_id is None and stored.entity_link_state is None
            assert stored.created_by_user_id == actor.user_id
        # Unlinked mentions resolve to spans, so the scan can show and select them.
        mentions = await _fetch_text_mentions(db, page.source_id)
        spans = _match_text_mention_spans(_layout("Eva met someone.", "Jan Novak signed."), mentions)
        assert {(span.mention_id, span.start_line_id, span.entity_id) for span in spans} == {
            (single.mention_id, "l1", None), (batch[0].mention_id, "l0", None),
        }


@pytest.mark.asyncio
async def test_text_patch_keeps_the_link_and_its_verification(migrated_postgres):
    async with async_sessionmaker(migrated_postgres, expire_on_commit=False)() as session:
        db = postgres_database(session)
        actor, editor = await _actor(db, "Verifier"), await _actor(db, "Editor")
        page = await _page(db, actor)
        person = await db.entities.create(EntityCreateRequest(entity_type=EntityType.person, name="Jan Novak"), actor)
        mention = await db.text_mentions.create(
            TextMentionCreateRequest(
                name="Jan", context="Jan Novak wrote.", entity_id=person.entity_id,
                entity_link_state=EntityLinkState.manual, source_id=page.source_id,
            ),
            actor,
        )
        verified = await db.text_mentions.patch(
            mention.mention_id, TextMentionPatchRequest(entity_link_state=EntityLinkState.verified), actor,
        )
        assert verified is not None and verified.entity_link_state == EntityLinkState.verified

        changed = await db.text_mentions.patch(
            mention.mention_id, TextMentionPatchRequest(name="Jan Novak", context="Later Jan Novak signed."), editor,
        )

        assert changed is not None
        assert (changed.name, changed.context) == ("Jan Novak", "Later Jan Novak signed.")
        assert changed.entity_id == person.entity_id
        assert changed.entity_link_state == EntityLinkState.verified
        assert changed.entity_link_verified_by_user_id == actor.user_id
        assert changed.entity_link_verified_at == verified.entity_link_verified_at
        assert changed.last_touched_by_user_id == editor.user_id
        # The served spans follow the new words and line.
        spans = _match_text_mention_spans(
            _layout("Jan Novak wrote.", "Later Jan Novak signed."), await _fetch_text_mentions(db, page.source_id),
        )
        assert [(span.start_line_id, span.start_character, span.end_character) for span in spans] == [("l1", 6, 15)]
        assert spans[0].entity_link_state == EntityLinkState.verified

        # The batch form keeps omitted fields too, and null clears the context.
        (cleared,) = await db.text_mentions.patch_batch(
            [TextMentionPatchBatchItem(mention_id=mention.mention_id, context=None)], editor,
        )
        assert cleared is not None
        assert (cleared.name, cleared.context, cleared.entity_link_state) == ("Jan Novak", None, EntityLinkState.verified)

        # Repeating the current text records no new change.
        repeated = await db.text_mentions.patch(mention.mention_id, TextMentionPatchRequest(name="Jan Novak"), actor)
        assert repeated is not None and repeated.last_touched_at == cleared.last_touched_at
        assert repeated.last_touched_by_user_id == editor.user_id
