"""Typed media and page-subresource endpoints backed by Source records."""

import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import AnyUrl

from people_gator_api.schemas.pero import EntitySpanModel, PageLayoutModel
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentResponse,
    ImageCreateRequest,
    ImageListResponse,
    ImageResponse,
    PageCreateRequest,
    PageListResponse,
    PageResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.crud_services.entity_span_service import get_entity_spans
from people_gator_api.services.crud_services.image_content_service import (
    get_image_content,
)
from people_gator_api.services.crud_services.media_service import (
    create_document,
    create_image,
    create_page,
    get_document,
    get_document_by_path,
    get_image,
    get_image_by_url,
    get_page,
    get_page_by_path,
    list_images,
    list_documents,
    list_pages,
)
from people_gator_api.services.crud_services.page_image_service import get_page_image
from people_gator_api.services.crud_services.page_layout_service import get_page_layout
from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
    delete_source,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter()


# -----------------------------------------------------------------------------
# --- Page subresource helpers ------------------------------------------------
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# --- Documents ---------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
async def list_documents_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> DocumentListResponse:
    del user
    return await list_documents(
        session,
        after_id,
        limit,
        library=library,
        document_id=document_id,
    )


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
async def create_document_route(
    payload: DocumentCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> DocumentResponse:
    del user
    document, created = await create_document(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Document already registered")
    return document


@router.get(
    "/documents/lookup",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def lookup_document_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    library: str,
    document_id: uuid.UUID,
) -> DocumentResponse:
    """Fetch one document by its canonical library identity."""
    del user
    resolved = await get_document_by_path(session, library, document_id)
    if resolved is None:
        raise_api_error(404, "not_found", "Document not found")
    return resolved


@router.get(
    "/documents/{document_source_id:uuid}",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def get_document_route(
    document_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> DocumentResponse:
    del user
    document = await get_document(
        session,
        document_source_id,
    )
    if document is None:
        raise_api_error(404, "not_found", "Document not found")
    return document


@router.delete(
    "/documents/{document_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["documents"],
)
async def delete_document_route(
    document_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if (
        await get_document(
            session,
            document_source_id,
        )
        is None
    ):
        raise_api_error(404, "not_found", "Document not found")
    await delete_source(session, document_source_id)


# -----------------------------------------------------------------------------
# --- Pages -------------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/pages", response_model=PageListResponse, tags=["pages"])
async def list_pages_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> PageListResponse:
    del user
    return await list_pages(
        session,
        after_id,
        limit,
        library=library,
        document_id=document_id,
        page_id=page_id,
    )


@router.post(
    "/pages",
    response_model=PageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["pages"],
)
async def create_page_route(
    payload: PageCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> PageResponse:
    del user
    page, created = await create_page(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Page already registered")
    return page


@router.get("/pages/lookup", response_model=PageResponse, tags=["pages"])
async def lookup_page_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> PageResponse:
    """Fetch one page by its canonical library identity."""
    del user
    resolved = await get_page_by_path(
        session,
        library,
        page_id,
        document_id=document_id,
    )
    if resolved is None:
        raise_api_error(404, "not_found", "Page not found")
    return resolved


@router.get("/pages/{page_source_id:uuid}", response_model=PageResponse, tags=["pages"])
async def get_page_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> PageResponse:
    del user
    page = await get_page(session, page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return page


@router.get(
    "/pages/{page_source_id:uuid}/image",
    response_class=Response,
    tags=["pages"],
)
async def get_page_image_by_id_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    width: int | None = None,
) -> Response:
    """Stream one page image, optionally a cached JPEG derivative."""
    del user
    page = await get_page(session, page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    try:
        image = await get_page_image(str(page.url), max_width=width)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={"X-Cache": "HIT" if image.cache_hit else "MISS"},
    )


@router.get(
    "/pages/{page_source_id:uuid}/page-layout",
    response_model=PageLayoutModel,
    tags=["pages"],
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
    tags=["pages"],
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


@router.delete(
    "/pages/{page_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["pages"],
)
async def delete_page_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if await get_page(session, page_source_id) is None:
        raise_api_error(404, "not_found", "Page not found")
    await delete_source(session, page_source_id)


# -----------------------------------------------------------------------------
# --- Images ------------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/images", response_model=ImageListResponse, tags=["images"])
async def list_images_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    url: str | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> ImageListResponse:
    del user
    return await list_images(
        session,
        after_id,
        limit,
        url=url,
    )


@router.post(
    "/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["images"],
)
async def create_image_route(
    payload: ImageCreateRequest,
    session: WeaviateSessionDependency,
    user: DataIngestUserDependency,
) -> ImageResponse:
    del user
    image, created = await create_image(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Image already registered")
    return image


@router.get("/images/lookup", response_model=ImageResponse, tags=["images"])
async def lookup_image_route(
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
    url: AnyUrl,
) -> ImageResponse:
    """Fetch one image by its ``url``."""
    del user
    image = await get_image_by_url(
        session,
        str(url),
    )
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    return image


@router.get("/images/{image_id:uuid}", response_model=ImageResponse, tags=["images"])
async def get_image_route(
    image_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> ImageResponse:
    del user
    image = await get_image(session, image_id)
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    return image


@router.get("/images/{image_id:uuid}/content", response_class=Response, tags=["images"])
async def get_image_content_by_id_route(
    image_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: BrowseUserDependency,
) -> Response:
    del user
    image = await get_image(session, image_id)
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    try:
        content, media_type = await get_image_content(str(image.url))
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(content=content, media_type=media_type)


@router.delete(
    "/images/{image_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["images"],
)
async def delete_image_route(
    image_id: uuid.UUID,
    session: WeaviateSessionDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if await get_image(session, image_id) is None:
        raise_api_error(404, "not_found", "Image not found")
    await delete_source(session, image_id)
