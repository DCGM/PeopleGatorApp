"""Page-layout endpoints (PERO OCR structure per page Source).

Page layouts are sub-resources of pages: they are fetched either via the
page's Source UUID or through the shared ``/pages/lookup`` selectors.
"""

import uuid

from fastapi import APIRouter

from people_gator_api.schemas.pero import EntitySpanModel, PageLayoutModel
from people_gator_api.services.auth_service import BrowseUserDependency
from people_gator_api.services.crud_services.media_service import (
    get_page,
    get_page_by_path,
    get_page_by_url,
)
from people_gator_api.services.crud_services.page_layout_service import get_page_layout
from people_gator_api.services.crud_services.entity_span_service import get_entity_spans
from people_gator_api.services.crud_services.source_service import SourceResolutionError
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error


router = APIRouter(tags=["page-layouts"])


async def _fetch_layout_for_page(
    session: WeaviateSessionDependency,
    page_source_id: uuid.UUID,
) -> PageLayoutModel:
    """Fetch the stored layout for an already-resolved page."""
    try:
        return await get_page_layout(
            session,
            source_id=page_source_id,
            page_path=None,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)


async def _fetch_entity_spans_for_page(
    session: WeaviateSessionDependency,
    page_source_id: uuid.UUID,
) -> list[EntitySpanModel]:
    """Match directly linked entities against one page's stored OCR layout."""
    try:
        return await get_entity_spans(session, page_source_id)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)


@router.get(
    "/pages/{page_source_id:uuid}/page-layout",
    response_model=PageLayoutModel,
    tags=["page-layouts"],
)
async def get_page_layout_by_id_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> PageLayoutModel:
    """Fetch the page layout for one page by its Source UUID."""
    del user
    page = await get_page(session, page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_layout_for_page(session, page.page_source_id)


@router.get(
    "/pages/{page_source_id:uuid}/entity-spans",
    response_model=list[EntitySpanModel],
    tags=["page-layouts"],
)
async def get_entity_spans_by_id_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> list[EntitySpanModel]:
    """Return word-aligned fuzzy entity spans for one page Source UUID."""
    del user
    page = await get_page(session, page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_entity_spans_for_page(session, page.page_source_id)


@router.get(
    "/pages/lookup/page-layout",
    response_model=PageLayoutModel,
    tags=["page-layouts"],
)
async def lookup_page_layout_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    url: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
) -> PageLayoutModel:
    """Fetch one page layout by ``url`` or by ``library`` + ``document`` + ``page``."""
    del user
    if url is not None:
        if any(param is not None for param in (library, document, page)):
            raise_api_error(
                422,
                "ambiguous_selector",
                "Provide either url or the library/document/page selectors, not both",
            )
        resolved = await get_page_by_url(session, url)
    else:
        if library is None or document is None or page is None:
            raise_api_error(
                422,
                "missing_selector",
                "Provide either url or all of library, document and page",
            )
        resolved = await get_page_by_path(session, library, page, document_id=document)
    if resolved is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_layout_for_page(session, resolved.page_source_id)


@router.get(
    "/pages/lookup/entity-spans",
    response_model=list[EntitySpanModel],
    tags=["page-layouts"],
)
async def lookup_entity_spans_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    url: str | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
) -> list[EntitySpanModel]:
    """Return entity spans by page URL or archive identity."""
    del user
    if url is not None:
        if any(param is not None for param in (library, document, page)):
            raise_api_error(
                422,
                "ambiguous_selector",
                "Provide either url or the library/document/page selectors, not both",
            )
        resolved = await get_page_by_url(session, url)
    else:
        if library is None or document is None or page is None:
            raise_api_error(
                422,
                "missing_selector",
                "Provide either url or all of library, document and page",
            )
        resolved = await get_page_by_path(session, library, page, document_id=document)
    if resolved is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_entity_spans_for_page(session, resolved.page_source_id)
