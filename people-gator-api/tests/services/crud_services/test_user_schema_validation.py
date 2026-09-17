import pytest
from pydantic import ValidationError

from people_gator_api.schemas.users import UserCreateRequest, UserPatchRequest


def test_user_create_request_requires_identity_fields() -> None:
    with pytest.raises(ValidationError):
        UserCreateRequest.model_validate({"display_name": "user", "is_active": True})

    payload = UserCreateRequest(
        display_name="user",
        is_active=True,
        external_subject="subject",
        external_issuer="issuer",
    )

    assert payload.external_subject == "subject"
    assert payload.external_issuer == "issuer"


def test_user_patch_request_accepts_partial_updates() -> None:
    payload = UserPatchRequest(display_name="Updated user")

    assert payload.model_dump(exclude_unset=True) == {"display_name": "Updated user"}
