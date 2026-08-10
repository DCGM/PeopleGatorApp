import pytest
from pydantic import ValidationError

from people_gator_api.schemas.principals import (
    ModelAgentCreateRequest,
    PrincipalCreateRequest,
    UserCreateRequest,
)


def test_principal_create_request_accepts_shared_fields() -> None:
    payload = PrincipalCreateRequest(display_name="principal", is_active=True)

    assert payload.display_name == "principal"
    assert payload.is_active is True


def test_user_create_request_requires_user_specific_fields() -> None:
    with pytest.raises(ValidationError):
        UserCreateRequest(display_name="user", is_active=True)

    payload = UserCreateRequest(
        display_name="user",
        is_active=True,
        external_subject="subject",
        external_issuer="issuer",
    )

    assert payload.external_subject == "subject"
    assert payload.external_issuer == "issuer"


def test_model_agent_create_request_requires_model_agent_specific_fields() -> None:
    with pytest.raises(ValidationError):
        ModelAgentCreateRequest(display_name="agent", is_active=True)

    payload = ModelAgentCreateRequest(
        display_name="agent",
        is_active=True,
        model_slug="gpt-4o",
        model_version="2024-06-01",
    )

    assert payload.model_slug == "gpt-4o"
    assert payload.model_version == "2024-06-01"
