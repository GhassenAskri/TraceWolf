import asyncio

import pytest

import aicontrol

TRACE = "aicontrol.trace.name"
STEP = "aicontrol.step.name"


def spans_by_name(exporter):
    return {s.name: s for s in exporter.get_finished_spans()}


def test_calls_inside_a_trace_share_one_trace_id_and_carry_its_name(tracer, exporter):
    with aicontrol.trace("Summarize this PDF"):
        with tracer.start_as_current_span("first"):
            pass
        with tracer.start_as_current_span("second"):
            pass

    spans = spans_by_name(exporter)
    parent = spans["Summarize this PDF"]
    assert parent.parent is None
    for name in ("first", "second"):
        assert spans[name].context.trace_id == parent.context.trace_id
        assert spans[name].parent.span_id == parent.context.span_id
        assert spans[name].attributes[TRACE] == "Summarize this PDF"
    assert parent.attributes[TRACE] == "Summarize this PDF"


def test_calls_outside_a_trace_each_start_their_own_trace(tracer, exporter):
    with tracer.start_as_current_span("first"):
        pass
    with tracer.start_as_current_span("second"):
        pass

    spans = spans_by_name(exporter)
    assert spans["first"].context.trace_id != spans["second"].context.trace_id
    assert TRACE not in spans["first"].attributes


def test_step_names_label_the_calls_inside_the_block(tracer, exporter):
    with aicontrol.trace("Summarize this PDF"):
        with aicontrol.step("extract key points"):
            with tracer.start_as_current_span("first"):
                pass
        with aicontrol.step("write summary"):
            with tracer.start_as_current_span("second"):
                pass
        with tracer.start_as_current_span("third"):
            pass

    spans = spans_by_name(exporter)
    assert spans["first"].attributes[STEP] == "extract key points"
    assert spans["second"].attributes[STEP] == "write summary"
    assert STEP not in spans["third"].attributes


def test_step_works_without_a_trace_and_opens_no_span(tracer, exporter):
    with aicontrol.step("alone"):
        with tracer.start_as_current_span("call"):
            pass

    spans = spans_by_name(exporter)
    assert list(spans) == ["call"]
    assert spans["call"].attributes[STEP] == "alone"
    assert TRACE not in spans["call"].attributes


def test_nested_names_are_restored_when_the_inner_block_ends(tracer, exporter):
    with aicontrol.trace("outer"):
        with aicontrol.step("a"):
            with aicontrol.step("b"):
                assert aicontrol.current_step_name() == "b"
            assert aicontrol.current_step_name() == "a"
        with aicontrol.trace("inner"):
            assert aicontrol.current_trace_name() == "inner"
        assert aicontrol.current_trace_name() == "outer"

    assert aicontrol.current_trace_name() is None
    assert aicontrol.current_step_name() is None
    spans = spans_by_name(exporter)
    assert spans["inner"].parent.span_id == spans["outer"].context.span_id
    assert spans["inner"].context.trace_id == spans["outer"].context.trace_id


def test_names_are_restored_and_the_error_recorded_when_the_block_raises(tracer, exporter):
    with pytest.raises(RuntimeError):
        with aicontrol.trace("failing"):
            with aicontrol.step("boom"):
                raise RuntimeError("boom")

    assert aicontrol.current_trace_name() is None
    assert aicontrol.current_step_name() is None
    assert spans_by_name(exporter)["failing"].status.status_code.name == "ERROR"


def test_decorators_apply_to_sync_and_async_functions(tracer, exporter):
    @aicontrol.trace("sync trace")
    @aicontrol.step("sync step")
    def work():
        with tracer.start_as_current_span("sync call"):
            return aicontrol.current_trace_name(), aicontrol.current_step_name()

    @aicontrol.trace("async trace")
    @aicontrol.step("async step")
    async def async_work():
        with tracer.start_as_current_span("async call"):
            return aicontrol.current_trace_name(), aicontrol.current_step_name()

    assert work() == ("sync trace", "sync step")
    assert asyncio.run(async_work()) == ("async trace", "async step")
    assert aicontrol.current_trace_name() is None

    spans = spans_by_name(exporter)
    assert spans["sync call"].attributes[STEP] == "sync step"
    assert spans["async call"].attributes[TRACE] == "async trace"
    assert spans["async call"].context.trace_id == spans["async trace"].context.trace_id


def test_async_context_managers(tracer, exporter):
    async def run():
        async with aicontrol.trace("async block"):
            async with aicontrol.step("async step"):
                with tracer.start_as_current_span("call"):
                    pass

    asyncio.run(run())

    spans = spans_by_name(exporter)
    assert spans["call"].attributes[TRACE] == "async block"
    assert spans["call"].attributes[STEP] == "async step"
    assert spans["call"].parent.span_id == spans["async block"].context.span_id


def test_concurrent_tasks_keep_their_own_traces(tracer, exporter):
    async def work(name):
        async with aicontrol.trace(name):
            await asyncio.sleep(0)
            with tracer.start_as_current_span(f"call {name}"):
                await asyncio.sleep(0)

    async def run():
        await asyncio.gather(work("a"), work("b"))

    asyncio.run(run())

    spans = spans_by_name(exporter)
    assert spans["call a"].attributes[TRACE] == "a"
    assert spans["call b"].attributes[TRACE] == "b"
    assert spans["call a"].context.trace_id != spans["call b"].context.trace_id


def test_trace_carries_into_threads_started_with_run_in_thread(tracer, exporter):
    with aicontrol.trace("threaded"):
        aicontrol.run_in_thread(lambda: tracer.start_span("in thread").end()).result()

    spans = spans_by_name(exporter)
    assert spans["in thread"].context.trace_id == spans["threaded"].context.trace_id
    assert spans["in thread"].attributes[TRACE] == "threaded"


def test_trace_before_init_only_sets_the_name():
    with aicontrol.trace("early"):
        assert aicontrol.current_trace_name() == "early"
    assert aicontrol.current_trace_name() is None


@pytest.mark.parametrize("factory", [aicontrol.trace, aicontrol.step])
@pytest.mark.parametrize("name", ["", "   ", None, 3])
def test_names_must_be_non_empty_strings(factory, name):
    with pytest.raises(ValueError):
        factory(name)
