import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import aicontrol
from aicontrol import _config


@pytest.fixture
def no_project_env(monkeypatch):
    monkeypatch.delenv("AICONTROL_PROJECT", raising=False)
    monkeypatch.delenv("AICONTROL_ENDPOINT", raising=False)


def init_and_capture(**kwargs):
    """`init()` with an in-memory exporter; returns the resource attributes of one span."""
    exporter = InMemorySpanExporter()
    aicontrol.init(span_exporter=exporter, batch=False, **kwargs)
    try:
        provider = _config.get_tracer_provider()
        with provider.get_tracer("tests").start_as_current_span("call"):
            pass
        (span,) = exporter.get_finished_spans()
        return dict(span.resource.attributes)
    finally:
        aicontrol.shutdown()


def test_spans_carry_the_project(tracer, exporter):
    with tracer.start_as_current_span("call"):
        pass

    (span,) = exporter.get_finished_spans()
    assert span.resource.attributes["aicontrol.project"] == "test-project"
    assert span.resource.attributes["service.name"] == "test-project"


def test_second_init_is_ignored_and_does_not_add_an_exporter(tracer, exporter, caplog):
    first_provider = _config.get_tracer_provider()

    returned = aicontrol.init(project="other-project", span_exporter=exporter, batch=False)

    assert returned is first_provider
    with tracer.start_as_current_span("call"):
        pass
    assert len(exporter.get_finished_spans()) == 1
    assert "already initialised" in caplog.text


def test_second_init_needs_no_project(exporter, no_project_env, caplog):
    first_provider = _config.get_tracer_provider()

    assert aicontrol.init() is first_provider
    assert "already initialised" in caplog.text


def test_shutdown_allows_init_again(exporter):
    aicontrol.shutdown()

    aicontrol.init(project="again", span_exporter=exporter, batch=False)

    assert _config.get_tracer_provider() is not None


def test_sdk_does_not_replace_the_global_tracer_provider(exporter):
    from opentelemetry import trace

    assert trace.get_tracer_provider() is not _config.get_tracer_provider()


def test_exporter_endpoint_targets_otlp_traces_path():
    assert _config.traces_url("http://localhost:8000") == "http://localhost:8000/v1/traces"
    assert _config.traces_url("http://localhost:8000/") == "http://localhost:8000/v1/traces"


# --- the project is required ------------------------------------------------------------------


def test_init_without_a_project_raises_and_leaves_the_sdk_off(no_project_env):
    with pytest.raises(ValueError, match="AICONTROL_PROJECT"):
        aicontrol.init(span_exporter=InMemorySpanExporter(), batch=False)

    assert _config.get_tracer_provider() is None


def test_project_can_come_from_the_environment(no_project_env, monkeypatch):
    monkeypatch.setenv("AICONTROL_PROJECT", "from-env")

    assert init_and_capture()["aicontrol.project"] == "from-env"


def test_the_argument_beats_the_environment(no_project_env, monkeypatch):
    monkeypatch.setenv("AICONTROL_PROJECT", "from-env")

    assert init_and_capture(project="from-argument")["aicontrol.project"] == "from-argument"


def test_an_empty_environment_variable_counts_as_missing(no_project_env, monkeypatch):
    monkeypatch.setenv("AICONTROL_PROJECT", "")

    with pytest.raises(ValueError, match="needs a project"):
        aicontrol.init(span_exporter=InMemorySpanExporter(), batch=False)


def test_the_project_is_trimmed(no_project_env):
    assert init_and_capture(project="  my-project  ")["aicontrol.project"] == "my-project"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        3,
        "My Project",  # a name, not a slug
        "Support",  # capitals
        "support desk",
        "a_b",
        "a/b",
        "/",
        "a--b",
        "-a",
        "a-",
        "é",
        "x" * 65,
    ],
)
def test_only_a_slug_is_accepted_as_the_project(no_project_env, name):
    with pytest.raises(ValueError):
        aicontrol.init(project=name, span_exporter=InMemorySpanExporter(), batch=False)

    assert _config.get_tracer_provider() is None


def test_a_name_is_refused_with_the_slug_to_use_instead(no_project_env):
    with pytest.raises(ValueError) as error:
        aicontrol.init(project="My Project", span_exporter=InMemorySpanExporter(), batch=False)

    message = str(error.value)
    assert "'My Project' is not a slug" in message
    assert "slug of the project" in message and "AIControl UI" in message
    assert "Did you mean 'my-project'?" in message


def test_the_message_for_an_environment_variable_names_it(no_project_env, monkeypatch):
    monkeypatch.setenv("AICONTROL_PROJECT", "My Project")

    with pytest.raises(ValueError, match="AICONTROL_PROJECT"):
        aicontrol.init(span_exporter=InMemorySpanExporter(), batch=False)


def test_the_longest_allowed_slug_works(no_project_env):
    assert init_and_capture(project="x" * 64)["aicontrol.project"] == "x" * 64


# --- the old way of calling init() fails loudly ------------------------------------------------


def test_app_name_is_gone(no_project_env):
    with pytest.raises(TypeError, match="app_name"):
        aicontrol.init(app_name="my-bot", span_exporter=InMemorySpanExporter())


def test_arguments_are_keyword_only(no_project_env):
    # `init("http://localhost:8000", "my-bot")` used to be (endpoint, app_name): it must not
    # silently make the endpoint the project now.
    with pytest.raises(TypeError):
        aicontrol.init("my-project")


# --- the endpoint -------------------------------------------------------------------------------


def test_endpoint_is_the_argument_then_the_environment_then_the_default(
    no_project_env, monkeypatch
):
    assert _config.resolve_endpoint(None) == "http://localhost:8000"

    monkeypatch.setenv("AICONTROL_ENDPOINT", "http://from-env:9000")
    assert _config.resolve_endpoint(None) == "http://from-env:9000"
    assert _config.resolve_endpoint("http://explicit:1") == "http://explicit:1"

    monkeypatch.setenv("AICONTROL_ENDPOINT", "")
    assert _config.resolve_endpoint(None) == "http://localhost:8000"
