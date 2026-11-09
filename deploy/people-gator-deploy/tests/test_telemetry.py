"""Exercise the real Compose/env-file boundary with synthetic credentials only."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from people_gator_deploy import config
from people_gator_deploy.core import DeployError


class TelemetryTests(unittest.TestCase):
    def test_secret_validation_rejects_application_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env = {'GITHUB_REPOSITORY': 'DCGM/PeopleGatorApp', 'DEPLOY_DOCKER_CONTEXT': 'rootless',
                   'DEPLOY_DOMAIN': 'preview.example', 'DEPLOY_STATE_DIR': str(root / 'state'),
                   'DEPLOY_USERS_JSON': '{}',
                   'DEPLOY_TELEMETRY_ENV': 'PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=synthetic\nOTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic synthetic\n'}
            settings = config.load('pr', env)
            self.assertEqual(settings['telemetry_file'], str(root / 'state/telemetry.env'))
            files = dict((path.name, (content, mode)) for path, content, mode in config.secrets('pr', settings, env))
            self.assertEqual(files['telemetry.env'][1], 0o600)
            env['DEPLOY_TELEMETRY_ENV'] = 'PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD=secret\n'
            with self.assertRaisesRegex(DeployError, 'only unquoted RUM') as caught:
                config.secrets('pr', settings, env)
            self.assertNotIn('=secret', str(caught.exception))
            del env['DEPLOY_TELEMETRY_ENV']
            self.assertNotIn('telemetry_file', config.load('pr', env))

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose required')
    def test_each_stack_routes_telemetry_only_to_runtime_backend(self):
        assets = Path(__file__).resolve().parents[1] / 'src/people_gator_deploy/assets'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = root / 'telemetry.env'
            telemetry.write_text('PEOPLE_GATOR_API__RUM__ENABLED=true\nPEOPLE_GATOR_API__RUM__CLIENT_TOKEN=synthetic-rum\nOTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic synthetic\n')
            runtime = root / 'runtime.env'
            runtime.write_text('PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT=/data\n')
            (root / 'staging-login.html').write_text('')
            variables = {
                'PR_NUMBER': '94', 'COMMIT_SHA': 'abc123', 'RELEASE_TAG': 'v1.2.3',
                'BACKEND_IMAGE': 'backend:test', 'FRONTEND_IMAGE': 'frontend:test',
                'PREVIEW_HOST': 'pr.example', 'STAGING_HOST': 'staging.example', 'RELEASE_HOST': 'app.example',
                'DB_NAME': 'test', 'DB_USER': 'test', 'DB_PASSWORD': 'synthetic',
                'USERS_FILE': str(runtime), 'RUNTIME_FILE': str(runtime), 'MIGRATION_FILE': str(runtime),
                'CORS_ORIGIN_REGEX': '^https://app.example$', 'TELEMETRY_FILE': str(telemetry),
                'APPLICATION_OTEL_NETWORK': 'logging', 'DATABASE_NETWORK': 'database',
            }
            environment = {key: os.environ[key] for key in ('PATH', 'HOME') if key in os.environ}
            environment.update(variables)
            for name in ('pr', 'staging', 'release'):
                with self.subTest(environment=name):
                    result = subprocess.run(['docker', 'compose', '-f', str(assets / f'compose.{name}.yaml'),
                                             '--profile', 'tools', 'config', '--format', 'json'],
                                            env=environment, capture_output=True, text=True, check=True)
                    rendered = json.loads(result.stdout)
                    backend = rendered['services']['backend']
                    env = backend['environment']
                    self.assertEqual(env['PEOPLE_GATOR_API__RUM__CLIENT_TOKEN'], 'synthetic-rum')
                    self.assertEqual(env['OTEL_EXPORTER_OTLP_HEADERS'], 'Authorization=Basic synthetic')
                    self.assertEqual(env['PEOPLE_GATOR_API__DEPLOYMENT__ENVIRONMENT'], 'preview' if name == 'pr' else name)
                    self.assertEqual(env['PEOPLE_GATOR_API__DEPLOYMENT__VERSION'], 'v1.2.3' if name == 'release' else 'abc123')
                    self.assertIn('telemetry', backend['networks'])
                    self.assertEqual(rendered['networks']['telemetry']['name'], 'logging')
                    for service, settings in rendered['services'].items():
                        if service != 'backend':
                            self.assertNotIn('synthetic-rum', json.dumps(settings))
                            self.assertNotIn('OTEL_EXPORTER_OTLP_HEADERS', settings.get('environment', {}))
