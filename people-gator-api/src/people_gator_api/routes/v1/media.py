"""Typed media and page-subresource endpoints backed by Source records."""

import uuid

from fastapi import APIRouter, Response, status
from pydantic import AnyUrl

from people_gator_api.persistence.contracts import CreateResult
from people_gator_api.routes.v1.query_dependencies import (
    DocumentListFilterDependency,
    ImageListFilterDependency,
    ListRequestDependency,
    PageListFilterDependency,
)
from people_gator_api.schemas.pero import PageLayoutModel, TextMentionSpanModel
from people_gator_api.schemas.sources import (
    DocumentBatchCreateRequest,
    DocumentCreateRequest,
    DocumentListRequest,
    DocumentListResponse,
    DocumentLookupRequest,
    DocumentResponse,
    ImageBatchCreateRequest,
    ImageCreateRequest,
    ImageListRequest,
    ImageListResponse,
    ImageLookupRequest,
    ImageResponse,
    PageBatchCreateRequest,
    PageCreateRequest,
    PageListRequest,
    PageListResponse,
    PageLookupRequest,
    PageResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
)
from people_gator_api.services.database_service import (
    DatabaseDependency,
)
from people_gator_api.utils.http_errors import raise_api_error

router = APIRouter()


# -----------------------------------------------------------------------------
# --- Page subresource helpers ------------------------------------------------
# -----------------------------------------------------------------------------


async def _fetch_layout_for_page(
    page: PageResponse,
) -> PageLayoutModel:
    """Fetch the stored layout using an already-resolved page identity."""
    from people_gator_api.media.page_layout import (
        get_page_layout,
    )
    from people_gator_api.media.errors import SourceResolutionError

    try:
        return await get_page_layout(
            page.library,
            page.document_id,
            page.page_id,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)


async def _fetch_text_mention_spans_for_page(
    database: DatabaseDependency,
    page: PageResponse,
) -> list[TextMentionSpanModel]:
    """Match the page's text mentions against its stored OCR layout."""
    from people_gator_api.services.crud_services.text_mention_span_service import (
        get_text_mention_spans,
    )
    from people_gator_api.media.errors import SourceResolutionError

    try:
        return await get_text_mention_spans(
            database,
            page.source_id,
            library=page.library,
            document_id=page.document_id,
            page_id=page.page_id,
        )
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)


# -----------------------------------------------------------------------------
# --- Documents ---------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
async def list_documents_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    filter: DocumentListFilterDependency,
    list_request: ListRequestDependency,
) -> DocumentListResponse:
    del user
    return await database.sources.list_documents(
        DocumentListRequest(
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
    )


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
async def create_document_route(
    payload: DocumentCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> DocumentResponse:
    del user
    document, result = await database.sources.get_or_create_document(payload)
    if result == CreateResult.EXISTING:
        raise_api_error(409, "already_exists", "Document already registered")
    return document


@router.post(
    "/documents:batch",
    response_model=list[DocumentResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["documents"],
)
async def create_document_batch_route(
    payload: DocumentBatchCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> list[DocumentResponse]:
    del user
    return [
        response
        for response, _ in await database.sources.get_or_create_document_batch(payload)
    ]


@router.get(
    "/documents/lookup",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def lookup_document_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    library: str,
    document_id: uuid.UUID,
) -> DocumentResponse:
    """Fetch one document by its canonical library identity."""
    del user
    resolved = await database.sources.lookup_document(
        DocumentLookupRequest(library=library, document_id=document_id)
    )
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
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> DocumentResponse:
    del user
    document = await database.sources.get_document(document_source_id)
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
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if await database.sources.get_document(document_source_id) is None:
        raise_api_error(404, "not_found", "Document not found")
    await database.sources.delete(document_source_id)


# -----------------------------------------------------------------------------
# --- Pages -------------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/pages", response_model=PageListResponse, tags=["pages"])
async def list_pages_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    filter: PageListFilterDependency,
    list_request: ListRequestDependency,
) -> PageListResponse:
    del user
    return await database.sources.list_pages(
        PageListRequest(
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
    )


@router.post(
    "/pages",
    response_model=PageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["pages"],
)
async def create_page_route(
    payload: PageCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> PageResponse:
    del user
    page, result = await database.sources.get_or_create_page(payload)
    if result == CreateResult.EXISTING:
        raise_api_error(409, "already_exists", "Page already registered")
    return page


@router.post(
    "/pages:batch",
    response_model=list[PageResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["pages"],
)
async def create_page_batch_route(
    payload: PageBatchCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> list[PageResponse]:
    del user
    return [
        response
        for response, _ in await database.sources.get_or_create_page_batch(payload)
    ]


@router.get("/pages/lookup", response_model=PageResponse, tags=["pages"])
async def lookup_page_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
) -> PageResponse:
    """Fetch one page by its canonical library identity."""
    del user
    resolved = await database.sources.lookup_page(
        PageLookupRequest(
            library=library,
            document_id=document_id,
            page_id=page_id,
        )
    )
    if resolved is None:
        raise_api_error(404, "not_found", "Page not found")
    return resolved


@router.get("/pages/{page_source_id:uuid}", response_model=PageResponse, tags=["pages"])
async def get_page_route(
    page_source_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> PageResponse:
    del user
    page = await database.sources.get_page(page_source_id)
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
    database: DatabaseDependency,
    user: BrowseUserDependency,
    width: int | None = None,
) -> Response:
    """Stream one page image, optionally a cached JPEG derivative."""
    from people_gator_api.media.page_image import (
        get_page_image,
    )
    from people_gator_api.media.errors import SourceResolutionError

    del user
    page = await database.sources.get_page(page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    try:
        image = await get_page_image(
            page.library,
            page.document_id,
            page.page_id,
            max_width=width,
        )
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
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> PageLayoutModel:
    """Fetch the page layout for one page by its Source UUID."""
    del user
    page = await database.sources.get_page(page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_layout_for_page(page)


@router.get(
    "/pages/{page_source_id:uuid}/text-mentions-spans",
    response_model=list[TextMentionSpanModel],
    tags=["pages"],
)
async def get_text_mention_spans_by_id_route(
    page_source_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> list[TextMentionSpanModel]:
    """Return word-aligned fuzzy text-mention spans for one page Source UUID."""
    del user
    page = await database.sources.get_page(page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return await _fetch_text_mention_spans_for_page(database, page)


@router.delete(
    "/pages/{page_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["pages"],
)
async def delete_page_route(
    page_source_id: uuid.UUID,
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if await database.sources.get_page(page_source_id) is None:
        raise_api_error(404, "not_found", "Page not found")
    await database.sources.delete(page_source_id)


# -----------------------------------------------------------------------------
# --- Images ------------------------------------------------------------------
# -----------------------------------------------------------------------------


@router.get("/images", response_model=ImageListResponse, tags=["images"])
async def list_images_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    filter: ImageListFilterDependency,
    list_request: ListRequestDependency,
) -> ImageListResponse:
    del user
    return await database.sources.list_images(
        ImageListRequest(
            filter_=filter,
            limit=list_request.limit,
            return_total_count=list_request.return_total_count,
            cursor=list_request.cursor,
        )
    )


@router.post(
    "/images",
    response_model=ImageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["images"],
)
async def create_image_route(
    payload: ImageCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> ImageResponse:
    del user
    image, result = await database.sources.get_or_create_image(payload)
    if result == CreateResult.EXISTING:
        raise_api_error(409, "already_exists", "Image already registered")
    return image


@router.post(
    "/images:batch",
    response_model=list[ImageResponse],
    status_code=status.HTTP_201_CREATED,
    tags=["images"],
)
async def create_image_batch_route(
    payload: ImageBatchCreateRequest,
    database: DatabaseDependency,
    user: DataIngestUserDependency,
) -> list[ImageResponse]:
    del user
    return [
        response
        for response, _ in await database.sources.get_or_create_image_batch(payload)
    ]


@router.get("/images/lookup", response_model=ImageResponse, tags=["images"])
async def lookup_image_route(
    database: DatabaseDependency,
    user: BrowseUserDependency,
    url: AnyUrl,
) -> ImageResponse:
    """Fetch one image by its ``url``."""
    del user
    image = await database.sources.lookup_image(ImageLookupRequest(url=url))
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    return image


@router.get("/images/{image_id:uuid}", response_model=ImageResponse, tags=["images"])
async def get_image_route(
    image_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> ImageResponse:
    del user
    image = await database.sources.get_image(image_id)
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    return image


@router.get("/images/{image_id:uuid}/content", response_class=Response, tags=["images"])
async def get_image_content_by_id_route(
    image_id: uuid.UUID,
    database: DatabaseDependency,
    user: BrowseUserDependency,
) -> Response:
    from people_gator_api.media.image_content import (
        get_image_content,
    )
    from people_gator_api.media.errors import SourceResolutionError

    del user
    image = await database.sources.get_image(image_id)
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
    database: DatabaseDependency,
    user: AdminUserDependency,
) -> None:
    del user
    if await database.sources.get_image(image_id) is None:
        raise_api_error(404, "not_found", "Image not found")
    await database.sources.delete(image_id)
