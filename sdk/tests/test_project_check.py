"""A project that does not exist in AIControl is reported once in the logs, and never raises."""

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aicontrol
from aicontrol import _config
from aicontrol._project_check import EXPORTER_LOGGER, ProjectMonitor

NOT_FOUND = {"X-AIControl-Error": "project-not-found"}


class Stub:
    """A tiny HTTP server standing in for the AIControl API."""

    def __init__(self):
        self.seen: list[tuple[str, str]] = []  # (method, path)
        self.routes: dict[tuple[str, str], tuple[int, dict]] = {}
        self.delay = 0.0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_any(self, method):
                length = int(self.headers.get("content-length") or 0)
                self.rfile.read(length)
                stub.seen.append((method, self.path))
                if stub.delay and method == "GET":
                    time.sleep(stub.delay)
                status, headers = stub.routes.get((method, self.path), (200, {}))
                body = json.dumps({}).encode()
                self.send_response(status)
                for key, value in headers.items():
                    self.send_header(key, value)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                self.handle_any("GET")

            def do_POST(self):
                self.handle_any("POST")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True
        ).start()

    def respond(self, method, path, status, headers=None):
        self.routes[method, path] = (status, headers or {})

    def count(self, method, path=None):
        return sum(1 for m, p in self.seen if m == method and path in (None, p))

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    server = Stub()
    yield server
    server.close()


@pytest.fixture
def errors(caplog):
    """The ERROR records of the SDK's own logger."""
    caplog.set_level(logging.DEBUG)

    def read():
        return [r for r in caplog.records if r.name == "aicontrol" and r.levelno >= logging.ERROR]

    return read


def wait_for(condition, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def a_span():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("t").start_as_current_span("call"):
        pass
    return list(exporter.get_finished_spans())


# --- the check made at startup ------------------------------------------------------------------


def test_a_missing_project_is_logged_once_with_what_to_do(stub, errors):
    stub.respond("GET", "/api/projects/my-project", 404)
    monitor = ProjectMonitor("my-project", stub.url)

    monitor.check()
    monitor.check()

    (record,) = errors()
    message = record.getMessage()
    assert "'my-project'" in message and "does not exist" in message
    assert "slug" in message and "AIControl UI" in message and stub.url in message
    assert stub.count("GET", "/api/projects/my-project") == 2


def test_an_existing_project_logs_nothing_and_clears_an_earlier_report(stub, errors):
    stub.respond("GET", "/api/projects/p", 404)
    monitor = ProjectMonitor("p", stub.url)
    monitor.check()
    assert monitor.missing

    stub.respond("GET", "/api/projects/p", 200)
    monitor.check()

    assert not monitor.missing
    assert len(errors()) == 1  # only the first report


@pytest.mark.parametrize("status", [500, 503, 401])
def test_other_answers_do_not_claim_the_project_is_missing(stub, errors, status):
    stub.respond("GET", "/api/projects/p", status)

    ProjectMonitor("p", stub.url).check()

    assert errors() == []


def test_an_unreachable_api_never_raises_or_logs_an_error(errors):
    ProjectMonitor("p", "http://127.0.0.1:9").check()  # nothing listens on port 9

    assert errors() == []


# --- the answer to the export itself ------------------------------------------------------------


def test_repeated_refusals_are_logged_once_and_logged_again_after_a_recovery(stub, errors):
    stub.respond("POST", "/v1/traces", 404, NOT_FOUND)
    monitor = ProjectMonitor("p", stub.url)
    session = monitor.session()

    for _ in range(3):
        assert session.post(f"{stub.url}/v1/traces", data=b"x").status_code == 404
    assert len(errors()) == 1

    stub.respond("POST", "/v1/traces", 200)  # the project was created
    session.post(f"{stub.url}/v1/traces", data=b"x")
    assert not monitor.missing

    stub.respond("POST", "/v1/traces", 404, NOT_FOUND)  # and then deleted again
    session.post(f"{stub.url}/v1/traces", data=b"x")
    assert len(errors()) == 2


def test_a_404_without_the_marker_is_not_taken_for_a_missing_project(stub, errors):
    stub.respond("POST", "/v1/traces", 404)  # e.g. a wrong endpoint
    monitor = ProjectMonitor("p", stub.url)

    monitor.session().post(f"{stub.url}/v1/traces", data=b"x")

    assert errors() == [] and not monitor.missing


def test_the_exporter_does_not_retry_a_refusal_and_its_repeated_error_is_silenced(
    stub, errors, caplog
):
    stub.respond("POST", "/v1/traces", 404, NOT_FOUND)
    monitor = ProjectMonitor("p", stub.url)
    monitor.install_log_filter()
    try:
        exporter = OTLPSpanExporter(endpoint=f"{stub.url}/v1/traces", session=monitor.session())
        started = time.monotonic()
        results = [exporter.export(a_span()) for _ in range(3)]
        elapsed = time.monotonic() - started
    finally:
        monitor.close()

    assert [r.name for r in results] == ["FAILURE"] * 3
    assert stub.count("POST") == 3 and elapsed < 2  # one attempt each: a 404 is not retried
    assert len(errors()) == 1
    assert "Failed to export span batch" not in caplog.text


def test_the_exporters_own_error_stays_when_the_cause_is_not_a_missing_project(stub, caplog):
    stub.respond("POST", "/v1/traces", 404)  # no marker
    monitor = ProjectMonitor("p", stub.url)
    monitor.install_log_filter()
    try:
        exporter = OTLPSpanExporter(endpoint=f"{stub.url}/v1/traces", session=monitor.session())
        exporter.export(a_span())
    finally:
        monitor.close()

    assert "Failed to export span batch code: 404" in caplog.text


@pytest.mark.parametrize(
    ("template", "args"),
    [
        ("Failed to export span batch code: %s, reason: %s", ("{code}", "Not Found")),
        ("Failed to export spans batch code: %s, reason: %s", ("{code}", "Not Found")),
        ("Failed to export %s batch code: %s, reason: %s", ("spans", "{code}", "Not Found")),
    ],
    ids=["older", "newer", "templated (1.45)"],
)
def test_the_log_filter_knows_every_wording_of_the_exporters_error(template, args):
    monitor = ProjectMonitor("p", "http://127.0.0.1:9")
    monitor.install_log_filter()
    logger = logging.getLogger(EXPORTER_LOGGER)

    def record(code):
        values = tuple(code if a == "{code}" else a for a in args)
        return logger.makeRecord(
            EXPORTER_LOGGER, logging.ERROR, __file__, 1, template, values, None
        )

    try:
        assert logger.filter(record(404))  # not known to be missing yet: kept
        monitor.report_missing()
        assert not logger.filter(record(404))  # the refusal is silenced ...
        assert logger.filter(record(500))  # ... other failures are not
        assert logger.filter(record(4040))  # nor look-alike codes
    finally:
        monitor.close()


def test_closing_the_monitor_removes_its_log_filter():
    logger = logging.getLogger(EXPORTER_LOGGER)
    before = list(logger.filters)
    monitor = ProjectMonitor("p", "http://127.0.0.1:9")

    monitor.install_log_filter()
    assert len(logger.filters) == len(before) + 1
    monitor.close()

    assert logger.filters == before


# --- wired into init() ---------------------------------------------------------------------------


def test_init_checks_the_project_in_the_background_and_does_not_wait(stub, errors):
    stub.respond("GET", "/api/projects/support-desk", 404)
    stub.delay = 1.0  # a slow API must not slow the application down
    started = time.monotonic()

    aicontrol.init(project="support-desk", endpoint=stub.url, batch=False, instrument=False)
    try:
        assert time.monotonic() - started < 0.5
        assert wait_for(lambda: len(errors()) == 1, timeout=5)
        assert "support-desk" in errors()[0].getMessage()
    finally:
        aicontrol.shutdown()


def test_calls_for_a_missing_project_are_reported_once_and_the_app_is_unaffected(
    stub, errors, caplog
):
    stub.respond("GET", "/api/projects/p", 404)
    stub.respond("POST", "/v1/traces", 404, NOT_FOUND)
    provider = aicontrol.init(project="p", endpoint=stub.url, batch=False, instrument=False)
    try:
        assert wait_for(lambda: len(errors()) == 1)
        tracer = provider.get_tracer("app")
        for _ in range(3):  # exporting is synchronous here (batch=False)
            with tracer.start_as_current_span("work"):
                pass
        assert stub.count("POST", "/v1/traces") == 3
        assert len(errors()) == 1
        assert "Failed to export span batch" not in caplog.text
    finally:
        aicontrol.shutdown()


def test_an_existing_project_logs_nothing_through_init(stub, errors):
    aicontrol.init(project="p", endpoint=stub.url, batch=False, instrument=False)
    try:
        assert wait_for(lambda: stub.count("GET", "/api/projects/p") == 1)
    finally:
        aicontrol.shutdown()

    assert errors() == []


def test_a_custom_exporter_means_no_check_and_no_log_filter(stub):
    logger = logging.getLogger(EXPORTER_LOGGER)
    before = list(logger.filters)

    aicontrol.init(
        project="p", endpoint=stub.url, span_exporter=InMemorySpanExporter(), batch=False
    )
    try:
        assert logger.filters == before
    finally:
        aicontrol.shutdown()

    time.sleep(0.2)
    assert stub.seen == []


def test_shutdown_removes_the_log_filter(stub):
    logger = logging.getLogger(EXPORTER_LOGGER)
    before = list(logger.filters)

    aicontrol.init(project="p", endpoint=stub.url, batch=False, instrument=False)
    assert len(logger.filters) == len(before) + 1
    aicontrol.shutdown()

    assert logger.filters == before
    assert _config.get_tracer_provider() is None
