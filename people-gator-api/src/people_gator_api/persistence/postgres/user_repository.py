from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from typing import Any, cast as type_cast

from sqlalchemy import (
    delete,
    exists,
    func,
    or_,
    select,
)
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.persistence.contracts import (
    UserRepository,
)
from people_gator_api.schemas.missing import (
    is_missing,
)
from people_gator_api.schemas.users import (
    UserCreateRequest,
    UserListRequest,
    UserListResponse,
    UserPatchRequest,
    UserResponse,
)
from people_gator_api.persistence.postgres.models import (
    Entity,
    APIKey,
    Face,
    User,
)
from people_gator_api.persistence.postgres.utils import (
    commit,
    validate_cursor,
    cursor_fingerprint,
    decode_cursor,
    next_cursor,
    user_response,
    user_filters,
)


class PostgresUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self._session = session

    async def get(self, user_id: uuid.UUID) -> UserResponse | None:
        user = await self._session.get(User, user_id)
        return user_response(user) if user is not None else None

    async def list(self, query: UserListRequest) -> UserListResponse:
        filters = user_filters(query.filter_)
        fingerprint = cursor_fingerprint(query)
        cursor_id = decode_cursor(query.cursor, fingerprint)
        await validate_cursor(self._session, User, cursor_id, filters)
        total = None
        if query.return_total_count:
            total = (
                await self._session.scalar(select(func.count(User.id)).where(*filters))
                or 0
            )
        if query.limit == 0:
            return UserListResponse(items=[], limit=0, total_count=total)
        page_filters = [*filters]
        if cursor_id is not None:
            page_filters.append(User.id > cursor_id)
        rows = list(
            await self._session.scalars(
                select(User)
                .where(*page_filters)
                .order_by(User.id)
                .limit(query.limit + 1)
            )
        )
        page, cursor = next_cursor(rows, query.limit, User.id, fingerprint)
        return UserListResponse(
            items=[user_response(row) for row in page],
            limit=query.limit,
            total_count=total,
            cursor=cursor,
        )

    async def get_or_create(self, payload: UserCreateRequest) -> UserResponse:
        identity = json.dumps(
            [payload.external_issuer, payload.external_subject],
            separators=(",", ":"),
        )
        await self._session.execute(
            select(func.pg_advisory_xact_lock(func.hashtextextended(identity, 0)))
        )
        user = await self._session.scalar(
            select(User).where(
                User.external_issuer == payload.external_issuer,
                User.external_subject == payload.external_subject,
            )
        )
        if user is not None:
            return user_response(user)
        user = User(**payload.model_dump())
        self._session.add(user)
        await commit(self._session, "user create violates a persistence constraint")
        return user_response(user)

    async def patch(
        self, user_id: uuid.UUID, payload: UserPatchRequest
    ) -> UserResponse | None:
        user = await self._session.get(User, user_id)
        if user is None:
            return None
        if not is_missing(payload.display_name):
            user.display_name = payload.display_name
        if not is_missing(payload.is_active):
            user.is_active = payload.is_active
        if not is_missing(payload.external_subject):
            user.external_subject = payload.external_subject
        if not is_missing(payload.external_issuer):
            user.external_issuer = payload.external_issuer
        if not is_missing(payload.email):
            user.email = payload.email
        await commit(self._session, "user patch violates a persistence constraint")
        return user_response(user)

    async def delete(self, user_id: uuid.UUID) -> bool:
        return bool(await self.delete_batch([user_id]))

    async def delete_batch(self, user_ids: Sequence[uuid.UUID]) -> int:
        unique = list(dict.fromkeys(user_ids))
        if not unique:
            return 0
        referenced = await self._session.scalar(
            select(
                or_(
                    exists().where(Entity.user_id.in_(unique)),
                    exists().where(Entity.last_touched_by_user_id.in_(unique)),
                    exists().where(APIKey.user_id.in_(unique)),
                    exists().where(Face.user_id.in_(unique)),
                )
            )
        )
        if referenced:
            raise ValueError("cannot delete a user referenced by an entity or face")
        result = type_cast(
            CursorResult[Any],
            await self._session.execute(delete(User).where(User.id.in_(unique))),
        )
        await commit(self._session, "user delete failed")
        return int(result.rowcount or 0)
