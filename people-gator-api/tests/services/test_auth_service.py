"""Standalone OIDC protocol, durable sessions and PKCE attack regressions."""
import asyncio
import base64
import hashlib
import re
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlencode, urlsplit

import argon2
import pytest
from fastapi.testclient import TestClient
from joserfc.jwt import decode

from people_gator_auth import accounts, keys
from people_gator_auth.app import get_app
from people_gator_auth.settings import BrowserClient, settings
from people_gator_auth.store import Store

CALLBACK = 'https://app.test/auth-callback.html'
CLIENT = 'people-gator-browser'
SCOPE = 'openid profile offline_access'
PASSWORD_HASH = argon2.PasswordHasher(time_cost=1, memory_cost=8192).hash('password')


@pytest.fixture
def issuer(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'state_dir', tmp_path)
    monkeypatch.setattr(settings, 'issuer', 'https://issuer.test')
    monkeypatch.setattr(settings, 'clients', [BrowserClient(client_id=CLIENT,
        redirect_uris=[CALLBACK, 'https://app.test/docs'],
        post_logout_redirect_uris=['https://app.test/login.html'])])
    monkeypatch.setattr(keys, '_keyset', None)
    monkeypatch.setattr(keys, '_last_fetch_time', None)
    monkeypatch.setattr(keys, '_keyset_lock', asyncio.Lock())
    account = accounts.Account(hash=PASSWORD_HASH, scopes={'people-gator:browse'}, user_id=uuid.uuid4())
    save_account(account)
    with TestClient(get_app(), base_url=settings.issuer) as client:
        yield client, account


def save_account(account):
    (settings.state_dir/'accounts.json').write_bytes(accounts._adapter.dump_json({'alice': account}))


def authorization(**changes):
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    params = dict(client_id=CLIENT, redirect_uri=CALLBACK, response_type='code', scope=SCOPE,
                  state=secrets.token_urlsafe(16), nonce=secrets.token_urlsafe(16),
                  code_challenge=challenge, code_challenge_method='S256')
    params.update(changes)
    return verifier, params


def login_code(client, **changes):
    verifier, params = authorization(prompt='login', **changes)
    page = client.get('/token/authorize', params=params, follow_redirects=False)
    assert page.status_code == 200, page.text
    handle = re.search('name="interaction" value="([^"]+)"', page.text).group(1)
    response = client.post('/token/login', data=dict(interaction=handle, username='alice', password='password'), follow_redirects=False)
    assert response.status_code == 302, response.text
    callback = parse_qs(urlsplit(response.headers['location']).query)
    assert callback['state'] == [params['state']]
    return dict(grant_type='authorization_code', client_id=CLIENT, redirect_uri=CALLBACK,
                code=callback['code'][0], code_verifier=verifier), params


def tokens(client):
    form, params = login_code(client)
    response = client.post('/token/oidc', data=form)
    assert response.status_code == 200, response.text
    return response.json(), params


def refresh(client, token):
    return client.post('/token/oidc', data=dict(grant_type='refresh_token', client_id=CLIENT, refresh_token=token))


def test_code_exchange_identity_tokens_refresh_rotation_and_logout(issuer):
    client, account = issuer
    token, params = tokens(client)
    assert token['expires_in'] == settings.access_token_lifetime_seconds
    key_set = asyncio.run(keys.get_key_set())
    identity = decode(token['id_token'], key_set).claims
    assert identity['nonce'] == params['nonce'] and identity['aud'] == CLIENT
    access = decode(token['access_token'], key_set).claims
    assert access['uid'] == str(account.user_id) and access['scopes'] == 'people-gator:browse'
    assert access['token_use'] == 'access' and identity['token_use'] == 'id'
    renewed = refresh(client, token['refresh_token'])
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()['refresh_token'] != token['refresh_token']
    assert refresh(client, token['refresh_token']).json()['error'] == 'invalid_grant'
    # Replay also revokes the active refresh family and SSO session.
    assert refresh(client, renewed.json()['refresh_token']).status_code == 400
    token, _ = tokens(client)
    logout = client.get('/token/logout', params=dict(id_token_hint=token['id_token'],
        post_logout_redirect_uri='https://app.test/login.html', state='logout-state'), follow_redirects=False)
    assert logout.status_code == 302 and 'state=logout-state' in logout.headers['location']
    assert refresh(client, token['refresh_token']).status_code == 400


@pytest.mark.parametrize('changes', [
    {'code_challenge': ''}, {'code_challenge_method': 'plain'}, {'code_challenge_method': ''},
    {'code_challenge': 'short'}, {'redirect_uri': 'https://evil.test/callback'},
    {'redirect_uri': ''}, {'client_id': 'unknown'}, {'response_type': 'token'},
    {'scope': 'openid unknown'}, {'nonce': ''},
])
def test_invalid_authorization_never_collects_credentials(issuer, changes):
    client, _ = issuer
    _, params = authorization(**changes)
    response = client.get('/token/authorize', params=params, follow_redirects=False)
    assert response.status_code in {400, 302}
    assert '<form' not in response.text
    assert not response.headers.get('location', '').startswith('https://evil.test')
    assert 'access_token' not in response.text


@pytest.mark.parametrize('changes', [
    {'code_verifier': 'wrong'*12}, {'code_verifier': ''}, {'client_id': 'unknown'},
    {'redirect_uri': 'https://app.test/docs'}, {'code': 'unknown'},
])
def test_exchange_rejects_wrong_proof_client_redirect_and_code(issuer, changes):
    client, _ = issuer
    form, _ = login_code(client)
    form.update(changes)
    response = client.post('/token/oidc', data=form)
    assert response.status_code == 400 and 'access_token' not in response.json()


def test_code_expiry_replay_and_atomic_redemption(issuer):
    client, _ = issuer
    form, _ = login_code(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: client.post('/token/oidc', data=form), range(6)))
    assert [r.status_code for r in results].count(200) == 1
    assert [r.status_code for r in results].count(400) == 5
    form, _ = login_code(client)
    with Store(settings.state_dir).transaction() as records:
        records.db.execute("UPDATE state SET expires = 0 WHERE kind = 'code'")
    assert client.post('/token/oidc', data=form).json()['error'] == 'invalid_grant'


def test_refresh_has_one_concurrent_winner_and_is_bound_to_client(issuer):
    client, _ = issuer
    token, _ = tokens(client)
    wrong = client.post('/token/oidc', data=dict(grant_type='refresh_token', client_id='unknown', refresh_token=token['refresh_token']))
    assert wrong.status_code == 400
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: refresh(client, token['refresh_token']), range(6)))
    assert [r.status_code for r in results].count(200) == 1


def test_disable_blocks_login_sso_refresh_and_does_not_revive_revoked_refresh(issuer):
    client, account = issuer
    token, _ = tokens(client)
    account.is_active = False
    save_account(account)
    assert refresh(client, token['refresh_token']).status_code == 400
    _, params = authorization(prompt='none')
    sso = client.get('/token/authorize', params=params, follow_redirects=False)
    assert 'error=login_required' in sso.headers['location']
    account.is_active = True
    save_account(account)
    assert refresh(client, token['refresh_token']).status_code == 400


def test_sessions_and_refresh_survive_issuer_restart(issuer):
    client, _ = issuer
    token, _ = tokens(client)
    with TestClient(get_app(), base_url=settings.issuer) as restarted:
        restarted.cookies.update(client.cookies)
        _, params = authorization(prompt='none')
        sso = restarted.get('/token/authorize', params=params, follow_redirects=False)
        assert sso.status_code == 302 and 'code=' in sso.headers['location']
        assert refresh(restarted, token['refresh_token']).status_code == 200


def test_anonymous_prompt_none_returns_login_required_not_form(issuer):
    client, _ = issuer
    _, params = authorization(prompt='none')
    response = client.get('/token/authorize', params=params, follow_redirects=False)
    assert response.status_code == 302 and 'error=login_required' in response.headers['location']


@pytest.mark.parametrize('endpoint', ['/token/authorize', '/token/oidc'])
def test_duplicate_protocol_parameters_are_rejected(issuer, endpoint):
    client, _ = issuer
    if endpoint.endswith('authorize'):
        _, params = authorization()
        response = client.get(endpoint+'?'+urlencode(params)+'&nonce=second')
    else:
        form, _ = login_code(client)
        response = client.post(endpoint, content=urlencode(form)+'&code_verifier=second',
                               headers={'Content-Type':'application/x-www-form-urlencoded'})
    assert response.status_code == 400


def test_form_is_csrf_bound_and_bad_password_does_not_issue_code(issuer):
    client, _ = issuer
    _, params = authorization()
    page = client.get('/token/authorize', params=params)
    assert "form-action 'self' https://app.test" in page.headers['content-security-policy']
    handle = re.search('name="interaction" value="([^"]+)"', page.text).group(1)
    denied = client.post('/token/login', data=dict(interaction=handle, username='alice', password='wrong'))
    assert 'Check your username and password.' in denied.text and 'location' not in denied.headers
    client.cookies.clear()
    denied = client.post('/token/login', data=dict(interaction=handle, username='alice', password='password'))
    assert denied.status_code == 400


def test_discovery_cors_revocation_and_password_grant_rejection(issuer):
    client, _ = issuer
    metadata = client.get('/.well-known/openid-configuration', headers={'Origin':'https://app.test'})
    assert metadata.headers['access-control-allow-origin'] == 'https://app.test'
    assert metadata.json()['code_challenge_methods_supported'] == ['S256']
    assert 'password' not in metadata.json()['grant_types_supported']
    rejected = client.post('/token/oidc', data=dict(grant_type='password', client_id=CLIENT, username='alice', password='password'))
    assert rejected.json()['error'] == 'unsupported_grant_type'
    assert client.post('/token/refresh', json={}).status_code == 404
    public = client.get('/.well-known/jwks.json').json()
    assert all('d' not in key for key in public['keys'])
    token, _ = tokens(client)
    revoked = client.post('/token/revoke', data=dict(client_id=CLIENT, token=token['refresh_token']))
    assert revoked.status_code == 200
    assert refresh(client, token['refresh_token']).status_code == 400
    assert client.get('/token/logout', params=dict(id_token_hint=token['id_token'],
        post_logout_redirect_uri='https://evil.test')).status_code == 400


def test_logout_while_disabled_or_cookie_lost_revokes_refresh_permanently(issuer):
    client, account = issuer
    token, _ = tokens(client)
    account.is_active = False
    save_account(account)
    client.cookies.clear()
    result = client.get('/token/logout', params=dict(id_token_hint=token['id_token'],
        post_logout_redirect_uri='https://app.test/login.html'), follow_redirects=False)
    assert result.status_code == 302
    account.is_active = True
    save_account(account)
    assert refresh(client, token['refresh_token']).status_code == 400


def test_opaque_credentials_are_not_stored_in_plaintext(issuer):
    client, _ = issuer
    form, _ = login_code(client)
    token = client.post('/token/oidc', data=form).json()
    stored = (settings.state_dir/'oidc.sqlite3').read_bytes()
    for secret in (form['code'], token['refresh_token'], client.cookies.get('pg_auth_session')):
        assert secret.encode() not in stored
