from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any
import uuid

import pytest

os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__USER", "user")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__PASSWORD", "password")
os.environ.setdefault("PEOPLE_GATOR_API__POSTGRES__DATABASE", "people_gator")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__ACCESS_KEY_ID", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__SECRET_ACCESS_KEY", "test")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__BUCKET_NAME", "bucket")
os.environ.setdefault("PEOPLE_GATOR_API__STORAGE__S3__REGION", "eu-central-1")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__URL", "http://localhost")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__REALM", "people-gator")
os.environ.setdefault("PEOPLE_GATOR_API__KEYCLOAK__AUDIENCE", "people-gator-api")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_PORT", "8080")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__HTTP_SECURE", "false")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_HOST", "localhost")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_PORT", "50051")
os.environ.setdefault("PEOPLE_GATOR_API__WEAVIATE__GRPC_SECURE", "false")

from people_gator_api.app import app
from people_gator_api.schemas.enums import SourceKind
from people_gator_api.schemas.search import SearchDocumentsQuery, SearchPagesQuery
from people_gator_api.services.crud_services import search_service
from people_gator_api.services.weaviate_service.archive_search import ArchiveCandidate


def _archive_search_double(
    candidate: ArchiveCandidate,
    expected_kind: SourceKind,
) -> Callable[..., Awaitable[list[ArchiveCandidate]]]:
    async def search_archive(
        _session: object,
        query: str,
        *,
        source_id: uuid.UUID | None,
        source_kind: SourceKind,
        limit: int,
    ) -> list[ArchiveCandidate]:
        assert query == "Ada"
        assert source_id is None
        assert source_kind is expected_kind
        assert limit == 5
        return [candidate]

    return search_archive


@pytest.mark.asyncio
async def test_search_pages_returns_page_only_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = ArchiveCandidate(
        source_id=uuid.uuid4(),
        kind=SourceKind.page,
        document_id=uuid.uuid4(),
        page_id=uuid.uuid4(),
        matching_score=0.75,
    )
    monkeypatch.setattr(
        search_service,
        "search_archive",
        _archive_search_double(candidate, SourceKind.page),
    )

    response = await search_service.search_pages(
        object(),  # pyright: ignore[reportArgumentType]
        SearchPagesQuery(q="Ada", limit=5),
    )

    assert response.items[0].page_id == candidate.page_id
    assert set(response.items[0].model_dump()) == {
        "source_id",
        "document_id",
        "page_id",
        "matching_score",
    }


@pytest.mark.asyncio
async def test_search_documents_returns_document_only_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = ArchiveCandidate(
        source_id=uuid.uuid4(),
        kind=SourceKind.document,
        document_id=uuid.uuid4(),
        page_id=None,
        matching_score=0.5,
    )
    monkeypatch.setattr(
        search_service,
        "search_archive",
        _archive_search_double(candidate, SourceKind.document),
    )

    response = await search_service.search_documents(
        object(),  # pyright: ignore[reportArgumentType]
        SearchDocumentsQuery(q="Ada", limit=5),
    )

    assert response.items[0].document_id == candidate.document_id
    assert set(response.items[0].model_dump()) == {
        "source_id",
        "document_id",
        "matching_score",
    }


def test_openapi_exposes_separate_archive_result_paths() -> None:
    paths: dict[str, Any] = app.openapi()["paths"]

    assert "/api/v1/search-pages" in paths
    assert "/api/v1/search-documents" in paths
    assert "/api/v1/search-archive" not in paths

    page_schema = paths["/api/v1/search-pages"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    document_schema = paths["/api/v1/search-documents"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert page_schema["$ref"].endswith("/PageSearchResultListResponse")
    assert document_schema["$ref"].endswith("/DocumentSearchResultListResponse")
