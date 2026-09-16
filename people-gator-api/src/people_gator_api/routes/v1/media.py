"""Typed page, document, and image endpoints backed by internal Source records."""

import uuid

from fastapi import APIRouter, Query, Response, status
from pydantic import AnyUrl

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
from people_gator_api.services.crud_services.image_content_service import (
    get_image_content,
)
from people_gator_api.services.crud_services.page_image_service import (
    get_page_image,
)
from people_gator_api.services.crud_services.media_service import (
    create_document,
    create_image,
    create_page,
    get_document,
    get_document_by_path,
    get_document_by_url,
    get_image,
    get_image_by_url,
    get_page,
    get_page_by_path,
    get_page_by_url,
    list_images,
    list_documents,
    list_pages,
)
from people_gator_api.services.crud_services.source_service import (
    SourceResolutionError,
    delete_source,
)
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error

router = APIRouter()


@router.get("/documents", response_model=DocumentListResponse, tags=["documents"])
async def list_documents_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> DocumentListResponse:
    del principal
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
    principal: DataIngestUserDependency,
) -> DocumentResponse:
    del principal
    document, created = await create_document(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Document already registered")
    return document


@router.get(
    "/documents/{document_source_id:uuid}",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def get_document_route(
    document_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> DocumentResponse:
    del principal
    document = await get_document(
        session,
        document_source_id,
    )
    if document is None:
        raise_api_error(404, "not_found", "Document not found")
    return document


@router.get(
    "/documents/object",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def get_document_object_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    url: AnyUrl | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
) -> DocumentResponse:
    """Fetch one document by ``url`` or by ``library`` + ``document``."""
    del principal
    if url is not None:
        if library is not None or document is not None:
            raise_api_error(
                422,
                "ambiguous_selector",
                "Provide either url or the library/document selectors, not both",
            )
        resolved = await get_document_by_url(session, str(url))
    else:
        if library is None or document is None:
            raise_api_error(
                422,
                "missing_selector",
                "Provide either url or both library and document",
            )
        resolved = await get_document_by_path(session, library, document)
    if resolved is None:
        raise_api_error(404, "not_found", "Document not found")
    return resolved


@router.delete(
    "/documents/{document_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["documents"],
)
async def delete_document_route(
    document_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> None:
    del principal
    if (
        await get_document(
            session,
            document_source_id,
        )
        is None
    ):
        raise_api_error(404, "not_found", "Document not found")
    await delete_source(session, document_source_id)


@router.get("/pages", response_model=PageListResponse, tags=["pages"])
async def list_pages_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    library: str | None = None,
    document_id: uuid.UUID | None = None,
    page_id: uuid.UUID | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> PageListResponse:
    del principal
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
    principal: DataIngestUserDependency,
) -> PageResponse:
    del principal
    page, created = await create_page(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Page already registered")
    return page


@router.get("/pages/object", response_model=PageResponse, tags=["pages"])
async def get_page_object_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    url: AnyUrl | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
) -> PageResponse:
    """Fetch one page by ``url`` or by ``library`` + ``document`` + ``page``."""
    del principal
    if url is not None:
        if any(param is not None for param in (library, document, page)):
            raise_api_error(
                422,
                "ambiguous_selector",
                "Provide either url or the library/document/page selectors, not both",
            )
        resolved = await get_page_by_url(session, str(url))
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
    return resolved


@router.get("/pages/{page_source_id:uuid}", response_model=PageResponse, tags=["pages"])
async def get_page_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageResponse:
    del principal
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
    principal: BrowseUserDependency,
    width: int | None = None,
) -> Response:
    """Stream one page image, optionally a cached JPEG derivative."""
    del principal
    page = await get_page(session, page_source_id)
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    try:
        image = await get_page_image(str(page.url), width=width)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={"X-Cache": "HIT" if image.cache_hit else "MISS"},
    )


@router.get("/pages/object/image", response_class=Response, tags=["pages"])
async def get_page_image_object_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    url: AnyUrl | None = None,
    library: str | None = None,
    document: uuid.UUID | None = None,
    page: uuid.UUID | None = None,
    width: int | None = None,
) -> Response:
    """Stream one page image selected by ``url`` or library/document/page."""
    del principal
    if url is not None:
        if any(param is not None for param in (library, document, page)):
            raise_api_error(
                422,
                "ambiguous_selector",
                "Provide either url or the library/document/page selectors, not both",
            )
        resolved = await get_page_by_url(session, str(url))
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
    try:
        image = await get_page_image(str(resolved.url), width=width)
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(
        content=image.content,
        media_type=image.media_type,
        headers={"X-Cache": "HIT" if image.cache_hit else "MISS"},
    )


@router.delete(
    "/pages/{page_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["pages"],
)
async def delete_page_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
) -> None:
    del principal
    if await get_page(session, page_source_id) is None:
        raise_api_error(404, "not_found", "Page not found")
    await delete_source(session, page_source_id)


@router.get("/images", response_model=ImageListResponse, tags=["images"])
async def list_images_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    url: str | None = None,
    limit: int = Query(default=50, ge=0),
    after_id: uuid.UUID | None = None,
) -> ImageListResponse:
    del principal
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
    principal: DataIngestUserDependency,
) -> ImageResponse:
    del principal
    image, created = await create_image(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Image already registered")
    return image


@router.get("/images/object", response_model=ImageResponse, tags=["images"])
async def get_image_object_route(
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
    url: AnyUrl,
) -> ImageResponse:
    """Fetch one image by its ``url``."""
    del principal
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
    principal: BrowseUserDependency,
) -> ImageResponse:
    del principal
    image = await get_image(session, image_id)
    if image is None:
        raise_api_error(404, "not_found", "Image not found")
    return image


@router.get(
    "/images/object/content",
    response_class=Response,
    tags=["images"],
)
async def get_image_content_route(
    url: AnyUrl,
    principal: BrowseUserDependency,
) -> Response:
    """Stream one stored image from the bucket (``image/{website}/{path}``)."""
    del principal
    try:
        content, media_type = await get_image_content(str(url))
    except SourceResolutionError as exc:
        raise_api_error(exc.status_code, exc.code, exc.message)
    return Response(content=content, media_type=media_type)


@router.get("/images/{image_id:uuid}/content", response_class=Response, tags=["images"])
async def get_image_content_by_id_route(
    image_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> Response:
    del principal
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
    principal: AdminUserDependency,
) -> None:
    del principal
    if await get_image(session, image_id) is None:
        raise_api_error(404, "not_found", "Image not found")
    await delete_source(session, image_id)
