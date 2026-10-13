import uuid

import pytest
from pydantic import ValidationError

from people_gator_api.persistence.postgres.source_repository import PostgresSourceRepository
from people_gator_api.persistence.postgres.utils import source_response
from people_gator_api.schemas.sources import DocumentCreateRequest, DocumentResponse, PageCreateRequest


def test_document_name_survives_all_internal_conversions():
    request = DocumentCreateRequest(library="mzk", document_id=uuid.uuid4(), name="  Archive album  ")
    assert request.name == "Archive album"
    source = PostgresSourceRepository._new(request.to_generic())
    source.id = uuid.uuid4()
    response = DocumentResponse.from_generic(source_response(source))
    assert response.name == "Archive album"
    assert response.document_id == request.document_id


@pytest.mark.parametrize("name", [None, "Title", "  Trimmed title  "])
def test_optional_document_names(name):
    request = DocumentCreateRequest(library="mzk", document_id=uuid.uuid4(), name=name)
    assert request.to_generic().name == (name.strip() if name else None)


@pytest.mark.parametrize("name", ["", " ", "\t\n"])
def test_blank_document_names_are_rejected(name):
    with pytest.raises(ValidationError):
        DocumentCreateRequest(library="mzk", document_id=uuid.uuid4(), name=name)


def test_name_is_not_a_page_field():
    with pytest.raises(ValidationError):
        PageCreateRequest(library="mzk", document_id=uuid.uuid4(), page_id=uuid.uuid4(), name="Title")
