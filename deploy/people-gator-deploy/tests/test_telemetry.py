"""OTel and RUM settings reach only the API runtime container, through the rendered telemetry file."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from people_gator_deploy import config

DOCUMENT = {"host": "app.example", "database": "postgresql://app:pw@db:5432/app", "storage": {"local": {"root": "/data"}},
            "otel": {"endpoint": "http://collector:4318", "headers": "Authorization=Basic synthetic"},
            "rum": {"client_token": "synthetic-rum", "site": "o2.example", "session_sample_rate": 50}}


class TelemetryTests(unittest.TestCase):
    def test_telemetry_file_is_rendered_from_otel_and_rum(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = config.load("staging", {"GITHUB_REPOSITORY": "DCGM/PeopleGatorApp", "DEPLOY_STATE_DIR": directory,
                                               "DEPLOY_CONFIG": json.dumps(DOCUMENT)})
            files = {path.name: (content, mode) for path, content, mode in config.files("staging", settings)}
            lines = files["telemetry.env"][0].splitlines()
            self.assertEqual(lines, [
                "PEOPLE_GATOR_API__OTEL__ENABLED=true",
                "PEOPLE_GATOR_API__OTEL__TRACES_ENDPOINT=http://collector:4318/v1/traces",
                "PEOPLE_GATOR_API__OTEL__LOGS_ENDPOINT=http://collector:4318/v1/logs",
                "PEOPLE_GATOR_API__OTEL__METRICS_ENDPOINT=http://collector:4318/v1/metrics",
                "OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic synthetic",
                "PEOPLE_GATOR_API__RUM__ENABLED=true",
                "PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=synthetic-rum",
                "PEOPLE_GATOR_API__RUM__SITE=o2.example",
                "PEOPLE_GATOR_API__RUM__SESSION_SAMPLE_RATE=50",
            ])
            self.assertEqual(files["telemetry.env"][1], 0o600)
            self.assertNotIn("synthetic", files["runtime.env"][0])

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose required')
    def test_each_stack_routes_telemetry_only_to_runtime_backend(self):
        assets = Path(__file__).resolve().parents[1] / 'src/people_gator_deploy/assets'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            telemetry = root / 'telemetry.env'
            telemetry.write_text('PEOPLE_GATOR_API__OTEL__ENABLED=true\nPEOPLE_GATOR_API__RUM__ENABLED=true\n'
                                 'PEOPLE_GATOR_API__RUM__CLIENT_TOKEN=synthetic-rum\nOTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic synthetic\n')
            runtime = root / 'runtime.env'
            # Raw env files keep dollar signs and quotes literal.
            runtime.write_text('PEOPLE_GATOR_API__STORAGE={"local": {"root": "/data"}, "s3": null}\nPEOPLE_GATOR_API__OPENROUTER__API_KEY=sk-$literal"\n')
            (root / 'staging-login.html').write_text('')
            variables = {
                'PR_NUMBER': '94', 'COMMIT_SHA': 'abc123', 'RELEASE_TAG': 'v1.2.3',
                'BACKEND_IMAGE': 'backend:test', 'FRONTEND_IMAGE': 'frontend:test',
                'PREVIEW_HOST': 'pr.example', 'STAGING_HOST': 'staging.example', 'RELEASE_HOST': 'app.example',
                'DB_HOST': 'pg.internal', 'DB_PORT': '6432', 'DB_NAME': 'test', 'DB_USER': 'test', 'DB_PASSWORD': 'synthetic',
                'USERS_FILE': str(runtime), 'RUNTIME_FILE': str(runtime), 'MIGRATION_FILE': str(runtime),
                'CORS_ORIGIN_REGEX': '^https://app.example$', 'TELEMETRY_FILE': str(telemetry),
            }
            environment = {key: os.environ[key] for key in ('PATH', 'HOME') if key in os.environ}
            environment.update(variables)
            for name in ('pr', 'pr-auth', 'staging', 'release'):
                with self.subTest(environment=name):
                    result = subprocess.run(['docker', 'compose', '-f', str(assets / f'compose.{name}.yaml'),
                                             '--profile', 'tools', 'config', '--format', 'json'],
                                            env=environment, capture_output=True, text=True, check=True)
                    rendered = json.loads(result.stdout)
                    backend = rendered['services']['backend']
                    env = backend['environment']
                    self.assertEqual(env['PEOPLE_GATOR_API__RUM__CLIENT_TOKEN'], 'synthetic-rum')
                    self.assertEqual(env['PEOPLE_GATOR_API__OTEL__ENABLED'], 'true')
                    self.assertEqual(env['OTEL_EXPORTER_OTLP_HEADERS'], 'Authorization=Basic synthetic')
                    # `compose config` re-escapes dollars in its output; the container gets the literal value.
                    self.assertEqual(env['PEOPLE_GATOR_API__OPENROUTER__API_KEY'].replace('$$', '$'), 'sk-$literal"')
                    self.assertEqual(env['PEOPLE_GATOR_API__STORAGE'], '{"local": {"root": "/data"}, "s3": null}')
                    self.assertEqual(env['PEOPLE_GATOR_API__DEPLOYMENT__ENVIRONMENT'], 'preview' if name.startswith('pr') else name)
                    self.assertEqual(env['PEOPLE_GATOR_API__DEPLOYMENT__VERSION'], 'v1.2.3' if name == 'release' else 'abc123')
                    if name != 'release':
                        self.assertEqual((env['PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__HOST'], env['PEOPLE_GATOR_API__PERSISTENCE__POSTGRES__PORT']),
                                         ('pg.internal', '6432'))
                    self.assertEqual(rendered['networks']['telemetry']['name'], 'logging')
                    self.assertEqual(rendered['networks']['database']['name'], 'people-gator-db')
                    self.assertEqual(backend['logging']['driver'], 'json-file')
                    for service, settings in rendered['services'].items():
                        if service != 'backend':
                            self.assertNotIn('synthetic-rum', json.dumps(settings))
                            self.assertNotIn('OTEL_EXPORTER_OTLP_HEADERS', settings.get('environment', {}))
                    # Previews ship a local volume by default; S3 would come through the same runtime file.
                    if name.startswith('pr'):
                        self.assertNotIn('PEOPLE_GATOR_API__STORAGE__LOCAL__ROOT', env)
                        self.assertEqual(rendered['services']['seed']['environment']['PEOPLE_GATOR_API__STORAGE'], env['PEOPLE_GATOR_API__STORAGE'])


if __name__ == "__main__":
    unittest.main()
