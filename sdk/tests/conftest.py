import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aicontrol
from aicontrol import _config


@pytest.fixture
def exporter():
    """Initialise the SDK with an in-memory exporter (synchronous export) and tear it down after."""
    exporter = InMemorySpanExporter()
    aicontrol.init(project="test-project", span_exporter=exporter, batch=False)
    yield exporter
    aicontrol.shutdown()


@pytest.fixture
def tracer(exporter):
    return _config.get_tracer_provider().get_tracer("tests")


def volumes_by_span_name(exporter) -> dict[str, str]:
    return {s.name: s.attributes["aicontrol.volume"] for s in exporter.get_finished_spans()}
