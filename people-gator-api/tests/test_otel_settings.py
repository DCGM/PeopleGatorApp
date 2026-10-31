"""Resolve complete exporter URLs in settings, including standard OTEL aliases."""
import os

import pytest

from people_gator_api.settings import Settings


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for name in os.environ:
        if name.startswith(('PEOPLE_GATOR_API__OTEL', 'OTEL_EXPORTER_')):
            monkeypatch.delenv(name)


@pytest.mark.parametrize('signal', ['traces', 'logs', 'metrics'])
@pytest.mark.parametrize('prefix', ['PEOPLE_GATOR_API__OTEL__', 'OTEL_EXPORTER_OTLP_'])
def test_complete_endpoint_environment_alias(monkeypatch, signal, prefix):
    endpoint = f'https://collector.example/api/default/v1/{signal}'
    monkeypatch.setenv(f'{prefix}{signal.upper()}_ENDPOINT', endpoint)
    assert getattr(Settings().otel, f'{signal}_endpoint') == endpoint


def test_standard_aliases_from_dotenv(tmp_path):
    (tmp_path / '.env').write_text('\n'.join(
        f'OTEL_EXPORTER_OTLP_{signal.upper()}_ENDPOINT=https://collector.example/custom/{signal}'
        for signal in ('traces', 'logs', 'metrics')
    ))
    otel = Settings().otel
    for signal in ('traces', 'logs', 'metrics'):
        assert getattr(otel, f'{signal}_endpoint') == f'https://collector.example/custom/{signal}'


def test_project_setting_wins_when_both_environment_names_exist(monkeypatch):
    monkeypatch.setenv('OTEL_EXPORTER_OTLP_TRACES_ENDPOINT', 'https://alias.example/traces')
    monkeypatch.setenv('PEOPLE_GATOR_API__OTEL__TRACES_ENDPOINT', 'https://project.example/traces')
    assert Settings().otel.traces_endpoint == 'https://project.example/traces'


def test_explicit_complete_urls_are_used_unchanged():
    config = Settings(otel={
        'traces_endpoint': 'https://collector.example/trace-ingest',
        'logs_endpoint': 'https://collector.example/log-ingest',
        'metrics_endpoint': 'https://collector.example/metric-ingest',
    })
    assert config.otel.traces_endpoint == 'https://collector.example/trace-ingest'
    assert config.otel.logs_endpoint == 'https://collector.example/log-ingest'
    assert config.otel.metrics_endpoint == 'https://collector.example/metric-ingest'
