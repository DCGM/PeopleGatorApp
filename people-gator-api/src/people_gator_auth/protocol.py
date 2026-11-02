"""Authlib OAuth/OIDC grants and small ASGI adapters, independent of the API."""
import secrets
import time
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import parse_qsl

from authlib.oauth2.rfc6749 import AuthorizationServer, ClientMixin, OAuth2Request
from authlib.oauth2.rfc6749.requests import OAuth2Payload
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc6749.errors import InvalidRequestError, InvalidScopeError
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oidc.core import UserInfo
from authlib.oidc.core.grants import OpenIDCode
from starlette.responses import JSONResponse, Response

from people_gator_auth.accounts import accounts
from people_gator_auth.keys import access_token
from people_gator_auth.settings import settings


OIDC_SCOPES = {"openid", "profile", "offline_access"}


class Payload(OAuth2Payload):
    def __init__(self, pairs):
        self._values = defaultdict(list)
        for key, value in pairs:
            self._values[key].append(value)

    @property
    def data(self):
        return {key: values[0] for key, values in self._values.items()}

    @property
    def datalist(self):
        return self._values


class ProtocolRequest(OAuth2Request):
    def __init__(self, method, path, pairs, headers=None):
        # Use the configured public issuer, never an untrusted forwarded Host.
        super().__init__(method, settings.issuer.rstrip("/") + path, headers=headers)
        self.payload = Payload(pairs)
        self.sid = ""

    @property
    def form(self):
        return self.payload.data if self.method == "POST" else {}

    @property
    def args(self):
        return self.payload.data if self.method == "GET" else {}


@dataclass
class Principal:
    username: str
    sid: str
    auth_time: int

    @property
    def account(self):
        account = accounts().get(self.username)
        return account if account and account.is_active else None


class Client(ClientMixin):
    def __init__(self, registration):
        self.registration = registration
        self.client_id = registration.client_id

    def get_client_id(self): return self.client_id
    def get_default_redirect_uri(self): return None  # explicit callback is mandatory
    def check_redirect_uri(self, uri): return uri in self.registration.redirect_uris
    def check_client_secret(self, secret): return False
    def check_endpoint_auth_method(self, method, endpoint): return method == "none"
    def check_response_type(self, response_type): return response_type == "code"
    def check_grant_type(self, grant_type): return grant_type in {"authorization_code", "refresh_token"}
    def get_allowed_scope(self, scope):
        requested = set((scope or "openid profile").split())
        if not requested <= OIDC_SCOPES | set(settings.api_scopes):
            raise InvalidScopeError()
        return " ".join(sorted(requested))


@dataclass
class Credential:
    secret: str
    data: dict

    @property
    def code_challenge(self): return self.data["code_challenge"]
    @property
    def code_challenge_method(self): return self.data["code_challenge_method"]
    def get_redirect_uri(self): return self.data["redirect_uri"]
    def get_scope(self): return self.data["scope"]
    def get_nonce(self): return self.data.get("nonce")
    def get_auth_time(self): return self.data["auth_time"]
    def get_acr(self): return None
    def get_amr(self): return ["pwd"]
    def check_client(self, client): return client.client_id == self.data["client_id"]
    def principal(self):
        user = Principal(self.data["username"], self.data["sid"], self.data["auth_time"])
        requested = set(self.get_scope().split()) - OIDC_SCOPES
        return user if user.account and requested <= user.account.scopes else None


class S256Challenge(CodeChallenge):
    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]

    def validate_code_challenge(self, grant, redirect_uri):
        data = grant.request.payload.data
        if not data.get("code_challenge") or data.get("code_challenge_method") != "S256":
            raise InvalidRequestError("S256 PKCE is required")
        super().validate_code_challenge(grant, redirect_uri)


class CodeGrant(AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]

    def save_authorization_code(self, code, request):
        user = request.user
        nonce = request.payload.data.get("nonce")
        if nonce:
            self.server.records.put("nonce", request.client.client_id + ":" + nonce, {},
                                    settings.authorization_code_lifetime_seconds)
        self.server.records.put("code", code, {
            "client_id": request.client.client_id, "redirect_uri": request.payload.redirect_uri,
            "scope": request.scope, "username": user.username, "sid": user.sid,
            "auth_time": user.auth_time, "nonce": request.payload.data.get("nonce"),
            "code_challenge": request.payload.data["code_challenge"], "code_challenge_method": "S256",
        }, settings.authorization_code_lifetime_seconds)

    def query_authorization_code(self, code, client):
        data = self.server.records.get("code", code)
        return Credential(code, data) if data and data["client_id"] == client.client_id else None

    def delete_authorization_code(self, code):
        self.server.records.delete("code", code.secret)

    def authenticate_user(self, code):
        return code.principal()


class RefreshGrant(RefreshTokenGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["none"]
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(self, secret):
        data = self.server.records.get("refresh", secret)
        if not data:
            spent = self.server.records.get("spent_refresh", secret)
            if spent and spent["client_id"] == self.request.client.client_id:
                # Reuse signals a compromised refresh family. Revoke its active
                # credentials and SSO session, not just the already-spent token.
                self.server.records.revoke_session_hash(spent["sid"])
            return None
        credential = Credential(secret, data) if data else None
        if credential and not credential.principal():
            self.server.records.revoke_session_hash(data["sid"])
            return None
        return credential

    def authenticate_user(self, token):
        return token.principal()

    def revoke_old_credential(self, token):
        self.server.records.put("spent_refresh", token.secret,
                                {"client_id": token.data["client_id"], "sid": token.data["sid"]},
                                settings.refresh_token_lifetime_seconds)
        self.server.records.delete("refresh", token.secret)


class IdentityToken(OpenIDCode):
    def __init__(self, server):
        super().__init__(require_nonce=True)
        self.server = server

    def exists_nonce(self, nonce, request):
        # Fresh OIDC transactions have independently random nonce values. Keep
        # spent nonces for the code lifetime, including after code redemption.
        return self.server.records.get("nonce", request.payload.client_id + ":" + nonce) is not None

    def resolve_client_private_key(self, client): return self.server.key_set.keys[0]
    def get_client_algorithm(self, client): return "ES256"
    def get_encode_header(self, client):
        return {"alg": "ES256", "kid": self.server.key_set.keys[0].kid, "typ": "JWT"}
    def get_client_claims(self, client):
        return {"iss": settings.issuer, "aud": client.client_id, "token_use": "id"}
    def generate_user_info(self, user, scope):
        return UserInfo(sub=user.username, name=user.username, uid=str(user.account.user_id), sid=user.sid)


class Server(AuthorizationServer):
    def __init__(self, records, key_set):
        super().__init__(list(OIDC_SCOPES) + settings.api_scopes)
        self.records, self.key_set = records, key_set
        self.register_grant(CodeGrant, [S256Challenge(required=True), IdentityToken(self)])
        self.register_grant(RefreshGrant)
        self.register_token_generator("default", self.tokens)

    def query_client(self, client_id):
        return next((Client(item) for item in settings.browser_clients() if item.client_id == client_id), None)

    def create_oauth2_request(self, request): return request
    def send_signal(self, *args, **kwargs): pass

    def handle_response(self, status, body, headers):
        response = JSONResponse(body, status_code=status) if isinstance(body, dict) else Response(body, status_code=status)
        response.headers.update(dict(headers))
        return response

    def tokens(self, grant_type, client, user, scope, expires_in=None, include_refresh_token=True):
        now = int(time.time())
        lifetime = settings.access_token_lifetime_seconds
        assigned = user.account.scopes & set(settings.api_scopes)
        requested = set(scope.split()) - OIDC_SCOPES
        if not requested <= assigned:
            raise InvalidScopeError()
        # This registered first-party resource audience receives the account's
        # assigned permissions when no narrower API scopes were requested.
        permissions = requested if requested else assigned
        if not permissions:
            raise InvalidScopeError("No application permissions are assigned")
        access = access_token(self.key_set, user.username, sorted(permissions), user.account.user_id, scope=scope)
        result = {"token_type": "Bearer", "access_token": access,
                  "expires_in": lifetime, "scope": scope}
        if include_refresh_token and "offline_access" in scope.split():
            result["refresh_token"] = secrets.token_urlsafe(48)
        return result

    def save_token(self, token, request):
        if secret := token.get("refresh_token"):
            user = request.user
            self.records.put("refresh", secret, {
                "username": user.username, "client_id": request.client.client_id,
                "scope": token["scope"], "sid": user.sid, "auth_time": user.auth_time,
            }, settings.refresh_token_lifetime_seconds)


def request_pairs(body: bytes):
    pairs = parse_qsl(body.decode(), keep_blank_values=True, max_num_fields=32)
    # Reject duplicates at both endpoints, including fields not checked by the
    # base OAuth authorization grant (nonce, verifier, code and refresh token).
    if len({name for name, _ in pairs}) != len(pairs):
        raise InvalidRequestError("Duplicate request parameter")
    return pairs
