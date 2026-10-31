from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
import pytest

from people_gator_api.app import get_app
from people_gator_api.settings import DeploymentSettings, RumSettings, settings
from people_gator_api.utils.opentelemetry import signal_endpoint, telemetry_resource


def test_runtime_config_only_publishes_browser_fields(monkeypatch):
    monkeypatch.setattr(settings, 'rum', RumSettings(enabled=True, client_token='synthetic-rum'))
    monkeypatch.setattr(settings, 'deployment', DeploymentSettings(
        environment='preview', version='abc123', commit='abc123', pr_number='94',
    ))
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_HEADERS', 'Authorization=private-exporter-secret')
    app = get_app()
    response = TestClient(app).get('/api/v1/rum-config')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    assert response.json() == {
        'enabled': True, 'clientToken': 'synthetic-rum',
        'site': 'openobserve.capturemyhand.com', 'organizationIdentifier': 'default',
        'applicationId': 'people-gator-app', 'service': 'people-gator-app',
        'env': 'preview', 'version': 'abc123', 'sessionSampleRate': 100,
        'context': {'commit': 'abc123', 'pr_number': '94'},
    }
    assert '/api/v1/rum-config' not in app.openapi()['paths']
    resource = telemetry_resource().attributes
    assert resource['service.name'] == 'people-gator-api'
    assert resource['service.version'] == 'abc123'
    assert resource['deployment.environment.name'] == 'preview'


def test_disabled_config_contains_no_token(monkeypatch):
    monkeypatch.setattr(settings, 'rum', RumSettings(client_token='synthetic-rum'))
    assert TestClient(get_app()).get('/api/v1/rum-config').json() == {'enabled': False}
    with pytest.raises(ValueError, match='dedicated browser client token'):
        RumSettings(enabled=True)


def test_fastapi_continues_browser_trace():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = get_app()
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    try:
        response = TestClient(app).get('/api/v1/health', headers={
            'traceparent': '00-0123456789abcdef0123456789abcdef-0123456789abcdef-01',
        })
        assert response.status_code == 200
        server = next(span for span in exporter.get_finished_spans() if span.kind.name == 'SERVER')
        assert server.context.trace_id == int('0123456789abcdef0123456789abcdef', 16)
        assert server.parent.span_id == int('0123456789abcdef', 16)
    finally:
        FastAPIInstrumentor.uninstrument_app(app)
        provider.shutdown()


def test_export_endpoint_preserves_org_prefix_and_signal_override(monkeypatch):
    monkeypatch.setattr(settings.otel, 'http_endpoint', 'https://openobserve.example/api/default')
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', raising=False)
    monkeypatch.delenv('OTEL_EXPORTER_OTLP_ENDPOINT', raising=False)
    assert signal_endpoint('traces') == 'https://openobserve.example/api/default/v1/traces'
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_ENDPOINT', 'http://collector:4318')
    assert signal_endpoint('traces') == 'http://collector:4318/v1/traces'
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', 'http://other-collector:4318/v1/traces')
    assert signal_endpoint('traces') == 'http://other-collector:4318/v1/traces'
