"""Shared typed Source selector for annotation list endpoints."""

import uuid
from typing import Annotated

from fastapi import Depends, Query
from pydantic import AnyUrl

from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
)
from people_gator_api.services.crud_services.source_resolution_service import (
    resolve_source_filter,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.utils.http_errors import raise_api_error


async def source_filter_dependency(
    session: WeaviateSessionDependency,
    source_id: uuid.UUID | None = None,
    page: str | None = Query(
        default=None,
        description="Canonical page identity: library/page_id or library/document_id/page_id.",
    ),
    document: str | None = Query(
        default=None,
        description="Canonical document identity: library/document_id.",
    ),
    image: AnyUrl | None = Query(
        default=None,
        description="Exact URL of an image Source.",
    ),
) -> uuid.UUID | None:
    """Resolve at most one public Source selector to its internal UUID."""
    try:
        return await resolve_source_filter(
            session,
            source_id=source_id,
            page=page,
            document=document,
            image=str(image) if image is not None else None,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)


SourceFilterDependency = Annotated[
    uuid.UUID | None,
    Depends(source_filter_dependency),
]
