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
    def test_private_file_validation_rejects_application_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = root / 'telemetry.env'
            users = root / 'users.json'
            users.write_text('{}')
            users.chmod(0o644)
            value = {
                'schema_version': 1, 'environment': 'pr', 'repository': 'DCGM/PeopleGatorApp',
                'state_dir': str(root / 'state'), 'docker_context': 'rootless',
                'domain': 'preview.example', 'web_network': 'web', 'database_network': 'db',
                'users_file': str(users), 'telemetry_file': str(telemetry),
                'infrastructure': {'mode': 'managed', 'project': 'infra', 'state_dir': str(root / 'state')},
            }
            path = root / 'config/config.json'
            telemetry.write_text('PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=synthetic\nOTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic synthetic\n')
            telemetry.chmod(0o600)
            config.validate(value, 'pr', path, inputs=True)
            telemetry.chmod(0o644)
            with self.assertRaisesRegex(DeployError, 'telemetry_file'):
                config.validate(value, 'pr', path, inputs=True)
            telemetry.chmod(0o600)
            telemetry.write_text('PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PASSWORD=secret\n')
            with self.assertRaisesRegex(DeployError, 'only unquoted RUM') as caught:
                config.validate(value, 'pr', path, inputs=True)
            self.assertNotIn('=secret', str(caught.exception))

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
