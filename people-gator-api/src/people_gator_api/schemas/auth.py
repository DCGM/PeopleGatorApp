from pydantic import BaseModel


class JwkKeyResponse(BaseModel):
    """A single JSON Web Key (public fields only)."""

    kty: str
    use: str | None = None
    kid: str | None = None
    alg: str | None = None
    n: str | None = None
    e: str | None = None
    x: str | None = None
    y: str | None = None
    crv: str | None = None


class JwksResponse(BaseModel):
    """JSON Web Key Set response (RFC 7517)."""

    keys: list[JwkKeyResponse]


class TokenResponse(BaseModel):
    """A signed JWT token response."""
    access_token: str
    refresh_token: str
    token_type: str


class OpenIDConfigurationResponse(BaseModel):
    """OpenID Connect discovery metadata for the People Gator token service."""

    issuer: str
    jwks_uri: str
    token_endpoint: str
    grant_types_supported: list[str]
    scopes_supported: list[str]
    subject_types_supported: list[str]
    token_endpoint_auth_methods_supported: list[str]

__all__ = [
    "JwkKeyResponse",
    "JwksResponse",
    "TokenResponse",
    "OpenIDConfigurationResponse",
]