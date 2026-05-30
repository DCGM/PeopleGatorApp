import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from joserfc import jwt
from joserfc.errors import JoseError
from joserfc.jwt import JWTClaimsRegistry
from sqlalchemy.ext.asyncio import AsyncSession

from people_gator_api.auth.jwks import JwksCache
from people_gator_api.db.engine import get_session
from people_gator_api.db.models.principal import Principal, User
from people_gator_api.settings import settings

logger = logging.getLogger(__name__)

_bearer = HTTPBearer()
_jwks_cache: JwksCache = JwksCache(settings.keycloak.jwks_uri)
_claims_registry: JWTClaimsRegistry = JWTClaimsRegistry()


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> Principal:
    """FastAPI dependency — verifies the Bearer JWT and resolves the PRINCIPAL row.

    For human users, the token is an OIDC ID/access token issued by Keycloak.
    The ``sub`` + ``iss`` claims are the stable identity key used to upsert the
    local ``User`` row.

    Raises ``HTTP 401`` for invalid/expired tokens and ``HTTP 403`` for
    deactivated accounts.
    """
    raw_token = credentials.credentials
    try:
        key_set = await _jwks_cache.get_key_set()
        token = jwt.decode(raw_token, key_set)
        _claims_registry.validate(token.claims)
    except JoseError as exc:
        logger.debug("JWT verification failed", exc_info=exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Annotate as dict[str, object] so .get()/.[] return typed object, not Unknown.
    claims: dict[str, object] = token.claims

    iss: str = str(claims.get("iss") or "")
    if iss != settings.keycloak.issuer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token issuer not trusted",
            headers={"WWW-Authenticate": "Bearer"},
        )

    sub: str = str(claims["sub"])
    display_name: str = str(
        claims.get("preferred_username") or claims.get("name") or sub
    )
    email: str | None = str(claims["email"]) if "email" in claims else None

    user, _ = await User.get_or_create(
        session=session,
        external_subject=sub,
        external_issuer=iss,
        display_name=display_name,
        email=email,
    )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    return user
