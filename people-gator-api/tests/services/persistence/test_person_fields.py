"""Person subtype: typed person contract, generic entities, filters, sorts and migration (#123)."""
import uuid
from datetime import date
from types import SimpleNamespace

import pytest
import pytest_asyncio
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from people_gator_api.persistence.contracts import EntityTypeConflictError, InvalidPersonFieldsError
from people_gator_api.persistence.postgres import postgres_database
from people_gator_api.persistence.postgres.schema import migration_config, validate_schema
from people_gator_api.schemas.entities import (
    EntityCreateRequest,
    EntityListRequest,
    EntityPatchRequest,
    PersonCreateRequest,
    PersonListFilter,
    PersonListRequest,
    PersonMergeBatchRequest,
    PersonPatchBatchItem,
    PersonPatchRequest,
)
from people_gator_api.schemas.search import QueryBase, SearchPeopleRequest
from people_gator_api.schemas.users import UserCreateRequest
from people_gator_api.services.auth_service import AuthContext

pytestmark = pytest.mark.asyncio

# Distinct names, dates and missing values so every sort produces its own order.
PEOPLE = {
    "ada": dict(first_name="Ada", surname="Novak", birth_date=date(1890, 3, 1), death_date=date(1962, 5, 4)),
    "bo": dict(first_name="Bohumil", middle_names="Karel  Jan", surname="Novák", birth_date=date(1901, 1, 1)),
    "cy": dict(first_name="Cyril", surname="Adler", death_date=date(1940, 7, 7)),
    "di": dict(first_name="Dita", surname="Novak", birth_date=date(1890, 3, 1), death_date=date(1950, 1, 1)),
    "ev": dict(),
}


@pytest_asyncio.fixture
async def persons(migrated_postgres):
    sessions = async_sessionmaker(migrated_postgres, expire_on_commit=False)
    async with sessions() as session:
        db = postgres_database(session)
        user = await db.users.get_or_create(UserCreateRequest(
            display_name="Person editor", is_active=True,
            external_subject=uuid.uuid4().hex, external_issuer="issue123",
        ))
        actor = AuthContext(user_id=user.user_id, api_key_id=None,
                            authentication_method="bearer", scopes=set())
        # Ascending fixed IDs make the entity_id tie-breaker explicit below.
        ids = {key: uuid.UUID(int=index + 1) for index, key in enumerate(PEOPLE)}
        for key, fields in PEOPLE.items():
            await db.entities.put_person(ids[key], PersonCreateRequest(name=f"Person {key}", **fields), actor)
        # A historical non-person row: the typed contract treats it as absent.
        other = uuid.UUID(int=99)
        await session.execute(text(
            "INSERT INTO pg_demo_entities (id, user_id, kind, name) VALUES (:id, :user, 'organization', 'Archive')"
        ), {"id": other, "user": user.user_id})
        await session.commit()
        yield SimpleNamespace(db=db, session=session, actor=actor, ids=ids, other=other)


def keys(r, items):
    names = {value: key for key, value in r.ids.items()}
    return [names[item.entity_id] for item in items]


async def listed(r, **values):
    filter_values = values.pop("filter", {})
    request = PersonListRequest(
        filter_=PersonListFilter(entity_id=[*r.ids.values(), r.other], **filter_values), **values,
    )
    return await r.db.entities.list_people(request)


async def test_typed_create_read_patch_clear_and_replace(persons):
    r = persons
    bo = await r.db.entities.get_person(r.ids["bo"])
    assert (bo.first_name, bo.middle_names, bo.surname) == ("Bohumil", "Karel Jan", "Novák")
    assert (bo.birth_date, bo.death_date) == (date(1901, 1, 1), None)
    ev = await r.db.entities.get_person(r.ids["ev"])
    assert (ev.first_name, ev.birth_date) == (None, None)

    patched = await r.db.entities.patch_person(r.ids["bo"], PersonPatchRequest(
        death_date=date(1970, 2, 2), middle_names=None,
    ), r.actor)
    assert (patched.first_name, patched.middle_names, patched.death_date) == ("Bohumil", None, date(1970, 2, 2))
    assert patched.last_touched_at is not None

    # A partial patch is validated against the stored birth date and changes nothing.
    with pytest.raises(InvalidPersonFieldsError, match="earlier than birth_date"):
        await r.db.entities.patch_person(r.ids["bo"], PersonPatchRequest(
            death_date=date(1900, 1, 1), name="Must not change",
        ), r.actor)
    after = await r.db.entities.get_person(r.ids["bo"])
    assert (after.name, after.death_date) == ("Person bo", date(1970, 2, 2))

    batch = await r.db.entities.patch_person_batch([
        PersonPatchBatchItem(entity_id=r.ids["ev"], surname="  Echo  "),
        PersonPatchBatchItem(entity_id=r.other, surname="Not a person"),
        PersonPatchBatchItem(entity_id=r.ids["cy"], death_date=None),
    ], r.actor)
    assert batch[0].surname == "Echo" and batch[1] is None and batch[2].death_date is None

    replaced = await r.db.entities.put_person(r.ids["ada"], PersonCreateRequest(
        name="Ada Replaced", surname="Novak",
    ), r.actor)
    assert replaced.created is False
    assert (replaced.person.surname, replaced.person.first_name, replaced.person.birth_date) == ("Novak", None, None)

    new_id = uuid.uuid4()
    created = await r.db.entities.put_person(new_id, PersonCreateRequest(
        name="Put Person", birth_date=date(2000, 1, 1),
    ), r.actor)
    assert created.created and (await r.db.entities.get_person(new_id)).birth_date == date(2000, 1, 1)
    made = await r.db.entities.create_person(PersonCreateRequest(name="Made", surname="Maker"), r.actor)
    assert made.surname == "Maker" and made.entity_type == "person"


async def test_generic_entities_keep_person_fields_unchanged(persons):
    r = persons
    # Shared payloads never touch person fields, including a generic PUT.
    await r.db.entities.patch(r.ids["ada"], EntityPatchRequest(short_description="Shared edit"), r.actor)
    await r.db.entities.put(r.ids["ada"], EntityCreateRequest(entity_type="person", name="Ada Shared"), r.actor)
    ada = await r.db.entities.get_person(r.ids["ada"])
    assert (ada.name, ada.short_description, ada.surname, ada.birth_date) == ("Ada Shared", None, "Novak", date(1890, 3, 1))
    created = await r.db.entities.create(EntityCreateRequest(entity_type="person", name="Shared Only"), r.actor)
    assert (await r.db.entities.get_person(created.entity_id)).surname is None


@pytest.mark.filterwarnings("ignore")
def test_generic_entity_requests_reject_person_sorts_and_filters():
    with pytest.raises(ValueError):
        EntityListRequest(limit=1, sort="surname")
    with pytest.raises(ValueError):
        EntityListRequest.model_validate({"limit": 1, "filter_": {"birth_date_from": "1900-01-01"}})
    assert PersonListRequest(limit=1, sort="surname").to_generic().filter_.entity_type == ["person"]


async def test_non_person_entities_are_absent_from_typed_methods(persons):
    r = persons
    assert await r.db.entities.entity_kinds([r.other, r.ids["ada"], uuid.uuid4()]) == {r.other: "organization", r.ids["ada"]: "person"}
    assert await r.db.entities.get_person(r.other) is None
    assert await r.db.entities.patch_person(r.other, PersonPatchRequest(name="X"), r.actor) is None
    assert await r.db.entities.merge_people(
        r.ids["ada"], PersonMergeBatchRequest(source_entity_ids=[r.other]), context=r.actor) is None
    assert await r.db.entities.delete_person(r.other, context=r.actor) is False
    with pytest.raises(EntityTypeConflictError):
        await r.db.entities.put_person(r.other, PersonCreateRequest(name="X"), r.actor)
    assert r.other not in {item.entity_id for item in (await listed(r, limit=100)).items}


async def test_merge_keeps_target_fields_unless_set(persons):
    r = persons
    merged = await r.db.entities.merge_people(
        r.ids["ada"], PersonMergeBatchRequest(source_entity_ids=[r.ids["bo"]]), context=r.actor)
    target = merged.merged_entity
    assert (target.first_name, target.birth_date, target.death_date) == ("Ada", date(1890, 3, 1), date(1962, 5, 4))
    assert target.middle_names is None

    with pytest.raises(InvalidPersonFieldsError):
        await r.db.entities.merge_people(r.ids["ada"], PersonMergeBatchRequest(
            source_entity_ids=[r.ids["cy"]], death_date=date(1800, 1, 1),
        ), context=r.actor)
    assert await r.db.entities.get_person(r.ids["cy"]) is not None  # rolled back

    merged = await r.db.entities.merge_people(r.ids["ada"], PersonMergeBatchRequest(
        source_entity_ids=[r.ids["cy"]], first_name="Adéla", death_date=None,
    ), context=r.actor)
    assert (merged.merged_entity.first_name, merged.merged_entity.death_date) == ("Adéla", None)
    assert merged.merged_entity.surname == "Novak"


async def test_delete_removes_subtype_row(persons):
    r = persons
    assert await r.db.entities.delete_person(r.ids["ev"], context=r.actor)
    assert await r.session.scalar(text(
        "SELECT count(*) FROM pg_demo_persons WHERE entity_id = :id"), {"id": r.ids["ev"]}) == 0
    await r.db.entities.delete(r.ids["cy"], context=r.actor)
    assert await r.db.entities.get_person(r.ids["cy"]) is None


@pytest.mark.parametrize(("filter_values", "expected"), [
    ({"birth_date_from": date(1890, 3, 1)}, ["ada", "bo", "di"]),
    ({"birth_date_to": date(1890, 3, 1)}, ["ada", "di"]),
    ({"birth_date_from": date(1890, 3, 2), "birth_date_to": date(1901, 1, 1)}, ["bo"]),
    ({"death_date_from": date(1940, 7, 7), "death_date_to": date(1950, 1, 1)}, ["cy", "di"]),
    ({"birth_date_from": date(1800, 1, 1), "death_date_from": date(1800, 1, 1)}, ["ada", "di"]),
])
async def test_inclusive_date_ranges_exclude_unknown_dates(persons, filter_values, expected):
    result = await listed(persons, filter=filter_values, return_total_count=True, sort="entity_id", limit=100)
    assert sorted(keys(persons, result.items)) == expected
    assert result.total_count == len(expected)


@pytest.mark.parametrize(("sort", "direction", "expected"), [
    # Adler; Novak Ada; Novák Bohumil (accent-insensitive); Novak Dita; unknown last.
    # Equal dates and unknown values fall back to entity_id ascending.
    ("surname", "asc", ["cy", "ada", "bo", "di", "ev"]),
    ("surname", "desc", ["di", "bo", "ada", "cy", "ev"]),
    ("birth_date", "asc", ["ada", "di", "bo", "cy", "ev"]),
    ("birth_date", "desc", ["bo", "ada", "di", "cy", "ev"]),
    ("death_date", "asc", ["cy", "di", "ada", "bo", "ev"]),
    ("death_date", "desc", ["ada", "di", "cy", "bo", "ev"]),
])
async def test_sorts_put_unknown_last_and_page_stably(persons, sort, direction, expected):
    r = persons
    ids = r.ids
    full = await listed(r, sort=sort, sort_direction=direction, limit=100)
    assert keys(r, full.items) == expected
    paged, cursor = [], None
    while True:
        page = await listed(r, sort=sort, sort_direction=direction, limit=2, cursor=cursor)
        paged.extend(page.items)
        cursor = page.cursor
        if cursor is None:
            break
    assert keys(r, paged) == expected

    found = await r.db.entities.search_people(SearchPeopleRequest(
        query=QueryBase(text=["Person"]), filter_=PersonListFilter(entity_id=list(ids.values())),
        sort=sort, sort_direction=direction, limit=100,
    ))
    assert keys(r, found.items) == expected


async def test_search_applies_date_filters(persons):
    found = await persons.db.entities.search_people(SearchPeopleRequest(
        query=QueryBase(text=["Person"]),
        filter_=PersonListFilter(entity_id=list(persons.ids.values()), birth_date_to=date(1895, 1, 1)),
        limit=10,
    ))
    assert sorted(keys(persons, found.items)) == ["ada", "di"]


async def test_migration_upgrades_existing_people_and_downgrades(migrated_postgres):
    async with migrated_postgres.begin() as connection:
        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)

        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0018", True))
        assert "pg_demo_persons" not in await connection.run_sync(
            lambda sync: __import__("sqlalchemy").inspect(sync).get_table_names())
        user_id, person_id, legacy_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        await connection.execute(text(
            "INSERT INTO pg_demo_users (id, display_name, is_active, external_subject, external_issuer) "
            "VALUES (:id, 'Legacy', true, :subject, 'issue123')"), {"id": user_id, "subject": uuid.uuid4().hex})
        await connection.execute(text(
            "INSERT INTO pg_demo_entities (id, user_id, kind, name, description) VALUES "
            "(:person, :user, 'person', 'Legacy Person', 'kept'), (:legacy, :user, 'organization', 'Archive', NULL)"),
            {"person": person_id, "legacy": legacy_id, "user": user_id})

        await connection.run_sync(lambda sync: migrate(sync, "head"))
        await connection.run_sync(validate_schema)
        rows = (await connection.execute(text(
            "SELECT entity_id, first_name, middle_names, surname, birth_date, death_date FROM pg_demo_persons"
        ))).all()
        assert rows == [(person_id, None, None, None, None, None)]
        assert await connection.scalar(text(
            "SELECT description FROM pg_demo_entities WHERE id = :id"), {"id": person_id}) == "kept"
        with pytest.raises(Exception, match="ck_pg_demo_persons_life_dates"):
            async with connection.begin_nested():
                await connection.execute(text(
                    "UPDATE pg_demo_persons SET birth_date = '1900-01-02', death_date = '1900-01-01'"))

        await connection.execute(text("ALTER TABLE pg_demo_persons DROP CONSTRAINT ck_pg_demo_persons_life_dates"))
        with pytest.raises(Exception, match="life-date constraint"):
            await connection.run_sync(validate_schema)
        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0018", True))
        assert await connection.scalar(text("SELECT count(*) FROM pg_demo_entities")) == 2
        await connection.run_sync(lambda sync: migrate(sync, "head"))
        assert await connection.scalar(text("SELECT count(*) FROM pg_demo_persons")) == 1


async def test_person_rows_exist_for_entity_only_writers(persons):
    """An older backend inserting only the entity row still yields a readable person."""
    r = persons
    user_id = await r.session.scalar(text("SELECT user_id FROM pg_demo_entities LIMIT 1"))
    legacy, transient = uuid.uuid4(), uuid.uuid4()
    await r.session.execute(text(
        "INSERT INTO pg_demo_entities (id, user_id, kind, name) VALUES "
        "(:legacy, :user, 'person', 'Legacy Writer'), (:transient, :user, 'person', 'Gone')"
    ), {"legacy": legacy, "transient": transient, "user": user_id})
    # Deleted before commit: the deferred trigger must not resurrect or fail on it.
    await r.session.execute(text("DELETE FROM pg_demo_entities WHERE id = :id"), {"id": transient})
    await r.session.commit()
    person = await r.db.entities.get_person(legacy)
    assert (person.name, person.surname, person.birth_date) == ("Legacy Writer", None, None)
    assert (await r.db.entities.patch_person(legacy, PersonPatchRequest(surname="Writer"), r.actor)).surname == "Writer"
    assert legacy in {item.entity_id for item in (await r.db.entities.list_people(PersonListRequest(limit=100))).items}
    # ORM-created people already have their row; the trigger leaves it as written.
    assert await r.session.scalar(text("SELECT count(*) FROM pg_demo_persons WHERE entity_id = ANY(:ids)"),
                                  {"ids": [legacy, transient, r.ids["ada"]]}) == 2


async def test_bootstrap_and_migration_backfill_people_without_rows(migrated_postgres):
    from people_gator_api.persistence.postgres.models import Base

    async with migrated_postgres.begin() as connection:
        def migrate(sync, target, downgrade=False):
            config = migration_config()
            config.attributes["connection"] = sync
            (command.downgrade if downgrade else command.upgrade)(config, target)

        # Revision 0019 had no trigger: an entity-only insert leaves an orphan.
        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0019", True))
        user_id, orphan = uuid.uuid4(), uuid.uuid4()
        await connection.execute(text(
            "INSERT INTO pg_demo_users (id, display_name, is_active, external_subject, external_issuer) "
            "VALUES (:id, 'Legacy', true, :subject, 'issue123')"), {"id": user_id, "subject": uuid.uuid4().hex})
        await connection.execute(text(
            "INSERT INTO pg_demo_entities (id, user_id, kind, name) VALUES (:id, :user, 'person', 'Orphan')"
        ), {"id": orphan, "user": user_id})
        orphans = text("SELECT count(*) FROM pg_demo_entities e WHERE kind = 'person' AND NOT EXISTS "
                       "(SELECT 1 FROM pg_demo_persons p WHERE p.entity_id = e.id)")
        assert await connection.scalar(orphans) == 1
        # Starting the ORM in bootstrap mode installs the trigger and backfills.
        await connection.run_sync(Base.metadata.create_all)
        assert await connection.scalar(orphans) == 0
        await connection.execute(text("DELETE FROM pg_demo_persons WHERE entity_id = :id"), {"id": orphan})
        await connection.run_sync(lambda sync: migrate(sync, "head"))
        assert await connection.scalar(orphans) == 0
        await connection.run_sync(validate_schema)

        # Validation fails loudly instead of serving unreadable people.
        async with connection.begin_nested() as nested:
            await connection.execute(text("ALTER TABLE pg_demo_entities DISABLE TRIGGER ensure_person"))
            with pytest.raises(Exception, match="person subtype trigger"):
                await connection.run_sync(validate_schema)
            await nested.rollback()
        async with connection.begin_nested() as nested:
            await connection.execute(text("DELETE FROM pg_demo_persons WHERE entity_id = :id"), {"id": orphan})
            with pytest.raises(Exception, match="lack a pg_demo_persons row"):
                await connection.run_sync(validate_schema)
            await nested.rollback()
        await connection.run_sync(lambda sync: migrate(sync, "d34a021b0019", True))
        assert not await connection.scalar(text(
            "SELECT count(*) FROM pg_trigger WHERE tgname = 'ensure_person' AND NOT tgisinternal"))
