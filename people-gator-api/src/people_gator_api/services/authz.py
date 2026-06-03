import logging
from dataclasses import dataclass
from typing import cast

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.auth.jwks import JwksCache
from people_gator_api.db.engine import get_session
from people_gator_api.db.models.principal import Principal, User
from people_gator_api.services.http_errors import raise_api_error
from people_gator_api.settings import settings

logger = logging.getLogger(__name__)

_required_bearer = HTTPBearer(auto_error=True)
_optional_bearer = HTTPBearer(auto_error=False)
_jwks_cache: JwksCache = JwksCache(settings.keycloak.jwks_uri)
_claims_registry: JWTClaimsRegistry = JWTClaimsRegistry()


@dataclass
class AuthContext:
    principal: Principal | None
    scopes: set[str]


async def _resolve_principal_from_token(raw_token: str, session: AsyncSession) -> AuthContext:
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

    sub: str = str(claims.get("sub") or "")
    if not sub:
        raise_api_error(401, "token_invalid", "Token missing subject")

    scope_claim: object = claims.get("scope", "")
    scopes: set[str]
    if isinstance(scope_claim, str):
        scopes = {value for value in scope_claim.split(" ") if value}
    elif isinstance(scope_claim, list):
        parsed_scopes: set[str] = set()
        for value in cast(list[object], scope_claim):
            if isinstance(value, str) and value:
                parsed_scopes.add(value)
        scopes = parsed_scopes
    else:
        scopes = set()

    display_name: str = str(claims.get("preferred_username") or claims.get("name") or sub)
    email: str | None = str(claims["email"]) if "email" in claims else None

    user, _ = await User.get_or_create(
        session=session,
        external_subject=sub,
        external_issuer=iss,
        display_name=display_name,
        email=email,
    )
    if not user.is_active:
        raise_api_error(403, "forbidden", "Account is deactivated")

    return AuthContext(principal=user, scopes=scopes)


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials = Depends(_required_bearer),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    return await _resolve_principal_from_token(credentials.credentials, session)


async def get_optional_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    if credentials is None:
        return AuthContext(principal=None, scopes={"people-gator:browse"})
    return await _resolve_principal_from_token(credentials.credentials, session)


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
