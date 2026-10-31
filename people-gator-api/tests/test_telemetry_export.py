"""Run the real app SDK bootstrap in a child process against a local OTLP sink.

The child isolates process-global instrumentors/providers from the pytest suite.
No application database, external collector or private credentials are needed.
"""
import gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import subprocess
import sys
from threading import Thread

import pytest

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import ExportLogsServiceRequest
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import ExportMetricsServiceRequest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest


CHILD = '''
import logging
from fastapi.testclient import TestClient
from opentelemetry import _logs, metrics, trace
import people_gator_api.schemas  # Match the CLI database/schema import order.
from people_gator_api.app import app
from people_gator_api.utils.opentelemetry import trace as traced

@traced("synthetic-child-operation")
async def operation():
    logging.getLogger("people_gator_api.telemetry_check").info(
        "synthetic correlated log", extra={"operation": "telemetry-check"},
    )
    try:
        raise ValueError("synthetic operation failure")
    except ValueError:
        logging.getLogger("people_gator_api.telemetry_check").exception("synthetic correlated error")
    metrics.get_meter("people_gator_api.telemetry_check").create_counter(
        "synthetic.operation.count",
    ).add(1)

@app.get("/api/v1/telemetry-check", include_in_schema=False)
async def telemetry_check():
    await operation()
    return {"status": "ok"}

response = TestClient(app).get("/api/v1/telemetry-check", headers={
    "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
})
assert response.status_code == 200
assert trace.get_tracer_provider().force_flush()
assert _logs.get_logger_provider().force_flush()
assert metrics.get_meter_provider().force_flush()
trace.get_tracer_provider().shutdown()
metrics.get_meter_provider().shutdown()
_logs.get_logger_provider().shutdown()
'''


@pytest.mark.parametrize(('environment', 'version', 'pr_number'), [
    ('preview', 'synthetic-commit', '94'),
    ('staging', 'synthetic-commit', ''),
    ('release', 'v1.2.3', ''),
])
def test_backend_directly_exports_correlated_traces_logs_and_metrics(environment, version, pr_number):
    requests = []

    class Sink(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            if self.headers.get('Content-Encoding') == 'gzip':
                body = gzip.decompress(body)
            requests.append((self.path, self.headers.get('Authorization'), body))
            self.send_response(200)
            self.send_header('Content-Type', 'application/x-protobuf')
            self.send_header('Content-Length', '0')
            self.end_headers()

        def log_message(self, *args):
            pass

    sink = ThreadingHTTPServer(('127.0.0.1', 0), Sink)
    worker = Thread(target=sink.serve_forever, daemon=True)
    worker.start()
    try:
        env = {key: value for key, value in os.environ.items() if not key.startswith('OTEL_')}
        env.update({
            'PEOPLE_GATOR_API__OTEL__ENABLED': 'true',
            'OTEL_EXPORTER_OTLP_TRACES_ENDPOINT': f'http://127.0.0.1:{sink.server_port}/custom/trace-ingest',
            'OTEL_EXPORTER_OTLP_LOGS_ENDPOINT': f'http://127.0.0.1:{sink.server_port}/custom/log-ingest',
            'OTEL_EXPORTER_OTLP_METRICS_ENDPOINT': f'http://127.0.0.1:{sink.server_port}/custom/metric-ingest',
            'PEOPLE_GATOR_API__DEPLOYMENT__ENVIRONMENT': environment,
            'PEOPLE_GATOR_API__DEPLOYMENT__VERSION': version,
            'PEOPLE_GATOR_API__DEPLOYMENT__COMMIT': 'synthetic-commit',
            'PEOPLE_GATOR_API__DEPLOYMENT__PR_NUMBER': pr_number,
            'OTEL_EXPORTER_OTLP_HEADERS': 'Authorization=Bearer%20synthetic-collector-token',
            'OTEL_EXPORTER_OTLP_TIMEOUT': '3',
        })
        result = subprocess.run(
            [sys.executable, '-c', CHILD], env=env, capture_output=True, text=True,
            cwd=Path(__file__).resolve().parents[1], timeout=30,
        )
        assert result.returncode == 0, result.stderr
    finally:
        sink.shutdown()
        sink.server_close()
        worker.join(timeout=5)

    def attributes(values):
        return {item.key: item.value.string_value for item in values}

    spans, logs, metric_names = [], [], []
    assert {path for path, _, _ in requests} == {'/custom/trace-ingest', '/custom/log-ingest', '/custom/metric-ingest'}
    for path, authorization, body in requests:
        assert authorization == 'Bearer synthetic-collector-token'
        message_type, resource_field, signal_field = {
            '/custom/trace-ingest': (ExportTraceServiceRequest, 'resource_spans', 'scope_spans'),
            '/custom/log-ingest': (ExportLogsServiceRequest, 'resource_logs', 'scope_logs'),
            '/custom/metric-ingest': (ExportMetricsServiceRequest, 'resource_metrics', 'scope_metrics'),
        }[path]
        message = message_type.FromString(body)
        for resource in getattr(message, resource_field):
            values = attributes(resource.resource.attributes)
            assert values['service.name'] == 'people-gator-api'
            assert values['deployment.environment.name'] == environment
            assert values['service.version'] == version
            assert values['vcs.ref.head.revision'] == 'synthetic-commit'
            assert values['people-gator.preview.pr'] == pr_number
            for scope in getattr(resource, signal_field):
                if path == '/custom/trace-ingest':
                    spans.extend(scope.spans)
                elif path == '/custom/log-ingest':
                    logs.extend(scope.log_records)
                else:
                    metric_names.extend(metric.name for metric in scope.metrics)

    child = next(span for span in spans if span.name == 'synthetic-child-operation')
    server = next(span for span in spans if span.kind == 2)
    assert child.trace_id.hex() == '0123456789abcdef0123456789abcdef'
    assert child.parent_span_id == server.span_id
    assert server.parent_span_id.hex() == '0123456789abcdef'
    correlated = [record for record in logs if record.body.string_value == 'synthetic correlated log']
    assert len(correlated) == 1
    assert correlated[0].trace_id == child.trace_id
    assert correlated[0].span_id == child.span_id
    assert attributes(correlated[0].attributes)['operation'] == 'telemetry-check'
    errors = [record for record in logs if record.body.string_value == 'synthetic correlated error']
    assert len(errors) == 1
    assert errors[0].trace_id == child.trace_id
    assert errors[0].span_id == child.span_id
    assert attributes(errors[0].attributes)['exception.type'] == 'ValueError'
    assert attributes(errors[0].attributes)['exception.message'] == 'synthetic operation failure'
    assert 'synthetic.operation.count' in metric_names
