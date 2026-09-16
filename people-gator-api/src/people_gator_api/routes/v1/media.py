"""Typed page, document, and image endpoints backed by internal Source records."""

import uuid

from fastapi import APIRouter, Query, status
from pydantic import AnyUrl

from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.sources import (
    DocumentCreateRequest,
    DocumentListResponse,
    DocumentResponse,
    DocumentSourceMetadata,
    ImageCreateRequest,
    ImageListResponse,
    ImageResponse,
    PageCreateRequest,
    PageListResponse,
    PageResponse,
    PageSourceMetadata,
    SourceResponse,
)
from people_gator_api.services.auth_service import (
    AdminUserDependency,
    BrowseUserDependency,
    DataIngestUserDependency,
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
from people_gator_api.services.crud_services.source_service import delete_source
from people_gator_api.services.database_service import WeaviateSessionDependency
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.services.sse import (
    BrokerDependency,
    DeletedResourceEvent,
    SseEventType,
)

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
    broker: BrokerDependency,
) -> DocumentResponse:
    del principal
    document, created = await create_document(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Document already registered")
    broker.publish_task(
        ("sources", document.document_source_id),
        event=SseEventType.SOURCE_CREATED,
        data=SourceResponse(
            source_id=document.document_source_id,
            source_type=SourceKind.document,
            uri=str(document.url),
            metadata=DocumentSourceMetadata(
                library=document.library,
                document=document.document_id,
                kramerius_url=document.url,
            ),
        ),
    )
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
    "/documents/by-url",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def get_document_by_url_route(
    url: AnyUrl,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> DocumentResponse:
    del principal
    document = await get_document_by_url(
        session,
        str(url),
    )
    if document is None:
        raise_api_error(404, "not_found", "Document not found")
    return document


@router.get(
    "/documents/{library}/{document_id:uuid}",
    response_model=DocumentResponse,
    tags=["documents"],
)
async def get_document_by_path_route(
    library: str,
    document_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> DocumentResponse:
    del principal
    document = await get_document_by_path(
        session,
        library,
        document_id,
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
    principal: AdminUserDependency,
    broker: BrokerDependency,
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
    broker.publish_task(
        ("sources", document_source_id),
        event=SseEventType.SOURCE_DELETED,
        data=DeletedResourceEvent(resource_id=document_source_id),
    )


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
    broker: BrokerDependency,
) -> PageResponse:
    del principal
    page, created = await create_page(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Page already registered")
    broker.publish_task(
        ("sources", page.page_source_id),
        event=SseEventType.SOURCE_CREATED,
        data=SourceResponse(
            source_id=page.page_source_id,
            source_type=SourceKind.page,
            uri=str(page.url),
            metadata=PageSourceMetadata(
                library=page.library,
                document=page.document_id,
                page=page.page_id,
                kramerius_url=page.url,
            ),
        ),
    )
    return page


@router.get("/pages/by-url", response_model=PageResponse, tags=["pages"])
async def get_page_by_url_route(
    url: AnyUrl,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageResponse:
    del principal
    page = await get_page_by_url(
        session,
        str(url),
    )
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return page


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
    "/pages/{library}/{document_id:uuid}/{page_id:uuid}",
    response_model=PageResponse,
    tags=["pages"],
)
async def get_page_by_full_path_route(
    library: str,
    document_id: uuid.UUID,
    page_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageResponse:
    del principal
    page = await get_page_by_path(
        session,
        library,
        page_id,
        document_id=document_id,
    )
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return page


@router.get(
    "/pages/{library}/{page_id:uuid}",
    response_model=PageResponse,
    tags=["pages"],
)
async def get_page_by_short_path_route(
    library: str,
    page_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> PageResponse:
    del principal
    page = await get_page_by_path(
        session,
        library,
        page_id,
    )
    if page is None:
        raise_api_error(404, "not_found", "Page not found")
    return page


@router.delete(
    "/pages/{page_source_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["pages"],
)
async def delete_page_route(
    page_source_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> None:
    del principal
    if await get_page(session, page_source_id) is None:
        raise_api_error(404, "not_found", "Page not found")
    await delete_source(session, page_source_id)
    broker.publish_task(
        ("sources", page_source_id),
        event=SseEventType.SOURCE_DELETED,
        data=DeletedResourceEvent(resource_id=page_source_id),
    )


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
    broker: BrokerDependency,
) -> ImageResponse:
    del principal
    image, created = await create_image(session, payload)
    if not created:
        raise_api_error(409, "already_exists", "Image already registered")
    broker.publish_task(
        ("sources", image.image_id),
        event=SseEventType.SOURCE_CREATED,
        data=SourceResponse(
            source_id=image.image_id,
            source_type=SourceKind.image,
            uri=str(image.url),
            metadata=None,
        ),
    )
    return image


@router.get("/images/by-url", response_model=ImageResponse, tags=["images"])
async def get_image_by_url_route(
    url: AnyUrl,
    session: WeaviateSessionDependency,
    principal: BrowseUserDependency,
) -> ImageResponse:
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


@router.delete(
    "/images/{image_id:uuid}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["images"],
)
async def delete_image_route(
    image_id: uuid.UUID,
    session: WeaviateSessionDependency,
    principal: AdminUserDependency,
    broker: BrokerDependency,
) -> None:
    del principal
    if await get_image(session, image_id) is None:
        raise_api_error(404, "not_found", "Image not found")
    await delete_source(session, image_id)
    broker.publish_task(
        ("sources", image_id),
        event=SseEventType.SOURCE_DELETED,
        data=DeletedResourceEvent(resource_id=image_id),
    )
