"""Issuer-owned account records; provisioned explicitly outside runtime startup."""
import uuid
from pydantic import BaseModel, Field, TypeAdapter
from people_gator_auth.settings import settings


class Account(BaseModel):
    hash: str = Field(repr=False)
    scopes: set[str]
    user_id: uuid.UUID
    is_active: bool = True


_adapter = TypeAdapter(dict[str, Account])


def accounts() -> dict[str, Account]:
    # Reread on every authorization/exchange so account policy changes take effect.
    return _adapter.validate_json((settings.state_dir / "accounts.json").read_bytes())
