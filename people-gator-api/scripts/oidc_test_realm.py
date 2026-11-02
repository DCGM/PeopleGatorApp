"""Write a synthetic, single-user Keycloak realm for the OIDC compatibility check.

Use only a disposable local Keycloak instance and an existing synthetic actor UUID.
The hardcoded claim mapper represents that one test identity, not production
user provisioning. Credentials are separate from the maintained resource seed.
"""
import argparse
import json
import uuid
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor-id', type=uuid.UUID, required=True)
    parser.add_argument('--app-origin', default='http://localhost:5194')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    origin = args.app_origin.rstrip('/')
    parsed = urlsplit(origin)
    if parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.path or parsed.query or parsed.fragment:
        parser.error('Compatibility fixture requires an isolated loopback app origin')

    def claim(name, value):
        return {'name': name, 'protocol': 'openid-connect', 'protocolMapper': 'oidc-hardcoded-claim-mapper',
                'config': {'claim.name': name, 'claim.value': value, 'jsonType.label': 'String',
                           'access.token.claim': 'true', 'id.token.claim': 'true'}}
    realm = {'realm': 'people-gator-oidc', 'enabled': True, 'sslRequired': 'none',
             'registrationAllowed': False, 'clients': [{
                 'clientId': 'people-gator-browser', 'publicClient': True,
                 'standardFlowEnabled': True, 'directAccessGrantsEnabled': False,
                 'redirectUris': [origin+'/auth-callback.html', origin+'/docs'], 'webOrigins': [origin],
                 'attributes': {'pkce.code.challenge.method': 'S256', 'post.logout.redirect.uris': origin+'/login.html'},
                 'protocolMappers': [claim('uid', str(args.actor_id)),
                     claim('permissions', 'people-gator:browse people-gator:annotate'),
                     {'name': 'resource-audience', 'protocol': 'openid-connect', 'protocolMapper': 'oidc-audience-mapper',
                      'config': {'included.custom.audience': 'localhost', 'access.token.claim': 'true', 'id.token.claim': 'false'}}],
             }], 'users': [{
                 'username': 'test', 'enabled': True, 'firstName': 'Preview', 'lastName': 'Reviewer',
                 'email': 'preview@example.invalid', 'emailVerified': True,
                 'credentials': [{'type': 'password', 'value': 'test', 'temporary': False}],
             }]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(realm, indent=2)+'\n')


if __name__ == '__main__':
    main()
