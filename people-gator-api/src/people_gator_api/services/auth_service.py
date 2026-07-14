import logging
from dataclasses import dataclass
from typing import TypeGuard, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, OpenIdConnect
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry
from weaviate import WeaviateAsyncClient

from people_gator_api.auth.jwks import JwksCache
from people_gator_api.services.crud_services.principal_service import get_or_create_user
from people_gator_api.services.database_service import get_session
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.settings import settings
from people_gator_api.services.weaviate_utils import StoredPrincipal

logger = logging.getLogger(__name__)
_jwks_cache: JwksCache = JwksCache(settings.keycloak.jwks_uri)
_claims_registry: JWTClaimsRegistry = JWTClaimsRegistry(
    issuer={"essential": True, "value": settings.keycloak.issuer},
    audience={"essential": True, "value": settings.keycloak.audience},
)

_required_oauth2 = OpenIdConnect(
    openIdConnectUrl=settings.keycloak.openid_configuration
)

_KNOWN_SCOPES = {
    'people-gator:browse',
    'people-gator:annotate',
    'people-gator:review',
    'people-gator:verify',
    'people-gator:ingest',
    'people-gator:admin'
}
    
    

@dataclass
class AuthContext:
    principal: StoredPrincipal | None
    scopes: set[str]


def _is_string_list(claim: object) -> TypeGuard[list[str]]:
    if not isinstance(claim, list):
        return False
    values: list[object] = cast(list[object], claim)  # Pyright cannot infer list element type here.
    return all(isinstance(value, str) for value in values)


def _parse_string_set(claim: object, separator: str | None = None) -> set[str]:
    if isinstance(claim, str):
        if separator is None:
            return {claim} if claim else set()
        return {value for value in claim.split(separator) if value}
    if _is_string_list(claim):
        return {value for value in claim if value}
    return set()


async def _resolve_principal_from_token(
    raw_token: str,
    session: WeaviateAsyncClient,
) -> AuthContext:
    claims: dict[str, object]
    try:
        key_set = await _jwks_cache.get_key_set()
        decoded = jwt.decode(raw_token, key_set)
        _claims_registry.validate(decoded.claims)
        claims = dict(decoded.claims)
    except JoseError as exc:
        logger.debug("JWT verification failed", exc_info=exc)
        raise_api_error(401, "token_invalid", "Invalid or expired token")

    iss: str = str(claims.get("iss") or "")
    if iss != settings.keycloak.issuer:
        raise_api_error(401, "token_invalid", "Token issuer not trusted")

    expected_audience: str | None = settings.keycloak.audience
    if not expected_audience:
        raise_api_error(500, "server_misconfigured", "Token audience is not configured")

    audiences: set[str] = _parse_string_set(claims.get("aud"))
    if expected_audience not in audiences:
        raise_api_error(401, "token_invalid", "Token audience not accepted")

    sub: str = str(claims.get("sub") or "")
    if not sub:
        raise_api_error(401, "token_invalid", "Token missing subject")

    scopes: set[str] = _parse_string_set(claims.get("scope", ""), separator=" ")

    display_name: str = str(claims.get("preferred_username") or claims.get("name") or sub)
    email: str | None = str(claims["email"]) if "email" in claims else None

    user = await get_or_create_user(
        session,
        external_subject=sub,
        external_issuer=iss,
        display_name=display_name,
        email=email,
    )
    if not user.is_active:
        raise_api_error(403, "forbidden", "Account is deactivated")

    return AuthContext(principal=user, scopes=scopes)


def empty_depends_on_openid_connect(
    request: Request,
) -> None:
    """
    This function exists solely to create a dependency on the OpenIdConnect security scheme,
    which ensures that the OpenAPI documentation includes the correct security requirements.
    The actual authentication logic is handled separately in the get_auth_context function.
    """
    return None

async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(empty_depends_on_openid_connect),
    session: WeaviateAsyncClient = Depends(get_session),
) -> AuthContext:
    if credentials is None:
        return AuthContext(principal=None, scopes=_KNOWN_SCOPES) # TODO: This is a temporary measure to allow unauthenticated access.
        #raise_api_error(401, "token_missing", "Authentication required")
    return await _resolve_principal_from_token(credentials.credentials, session)


async def get_optional_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(empty_depends_on_openid_connect),
    session: WeaviateAsyncClient = Depends(get_session),
) -> AuthContext:
    return AuthContext(principal=None, scopes={"people-gator:browse"})


def require_scopes(*required_scopes: str, allow_anonymous: bool = False):
    async def dependency(
        context: AuthContext = Depends(
            get_optional_auth_context if allow_anonymous else get_auth_context
        ),
    ) -> AuthContext:
        if not required_scopes:
            return context

        if allow_anonymous and context.principal is None:
            if all(scope == "people-gator:browse" for scope in required_scopes):
                return context
            raise_api_error(401, "token_missing", "Authentication required")

        missing = [scope for scope in required_scopes if scope not in context.scopes]
        if missing:
            raise_api_error(403, "insufficient_scope", "Missing required scope")
        return context

    return dependency
