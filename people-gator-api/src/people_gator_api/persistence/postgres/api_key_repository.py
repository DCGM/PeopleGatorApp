"""PostgreSQL registration and browsing of credential-free API-key identities."""

from sqlalchemy import ColumnElement, String, cast, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from people_gator_api.persistence.contracts import APIKeyRepository
from people_gator_api.persistence.postgres.models import APIKey, Source, Entity
from people_gator_api.persistence.postgres.utils import (
    commit,
    cursor_fingerprint,
    decode_cursor,
    next_cursor,
    validate_cursor,
)
from people_gator_api.schemas.api_keys import (
    APIKeyCreateRequest,
    APIKeyResponse,
    APIKeyListResponse,
    APIKeyListRequest,
)


def api_key_response(key: APIKey) -> APIKeyResponse:
    return APIKeyResponse(
        api_key_id=key.id,
        identifier=key.identifier,
        display_name=key.display_name,
        user_id=key.user_id,
    )


class PostgresAPIKeyRepository(APIKeyRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def get_or_create(self, payload: APIKeyCreateRequest) -> APIKeyResponse:
        # The unique index serializes registration across processes. Metadata may
        # change in configuration; the historical database identity stays stable.
        statement = insert(APIKey).values(**payload.model_dump())
        statement = statement.on_conflict_do_update(
            index_elements=[APIKey.identifier],
            set_={
                "display_name": statement.excluded.display_name,
                "user_id": statement.excluded.user_id,
            },
            where=or_(APIKey.user_id == statement.excluded.user_id,
                ~exists(select(1).where(Source.last_touched_by_api_key_id == APIKey.id))
                & ~exists(select(1).where(Entity.last_touched_by_api_key_id == APIKey.id))),
        ).returning(APIKey)
        key = (
            await self._session.scalars(
                statement, execution_options={"populate_existing": True}
            )
        ).one_or_none()
        if key is None:
            raise ValueError("cannot change the owner of a referenced API key")
        await commit(self._session, "API key registration failed")
        return api_key_response(key)

    async def list(self, query: APIKeyListRequest) -> APIKeyListResponse:
        filters: list[ColumnElement[bool]] = []
        if query.q:
            filters.append(
                or_(
                    APIKey.display_name.icontains(query.q, autoescape=True),
                    APIKey.identifier.icontains(query.q, autoescape=True),
                    cast(APIKey.id, String).icontains(query.q, autoescape=True),
                )
            )
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, APIKey, cursor_id, filters)
        total = (
            (
                await self._session.scalar(
                    select(func.count(APIKey.id)).where(*filters)
                )
                or 0
            )
            if query.return_total_count
            else None
        )
        if query.limit == 0:
            return APIKeyListResponse(items=[], limit=0, total_count=total)
        statement = (
            select(APIKey).where(*filters).order_by(APIKey.id).limit(query.limit + 1)
        )
        if cursor_id is not None:
            statement = statement.where(APIKey.id > cursor_id)
        rows = list(await self._session.scalars(statement))
        page, cursor = next_cursor(rows, query.limit, APIKey.id, fingerprint)
        return APIKeyListResponse(
            items=[api_key_response(key) for key in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )
