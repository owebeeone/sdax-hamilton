"""Regression coverage for the private Hamilton 1.90.0 pipeline correction."""

import asyncio
import inspect

import pytest

from sdax_hamilton import Driver
from sdax_hamilton._hamilton_pipeline import correct_copied_async_output_pipelines
from sdax_hamilton.hamilton_compat import _copy_function


def _corrected_nodes(fn):
    from hamilton.function_modifiers import base

    snapshot = _copy_function(fn)
    correct_copied_async_output_pipelines(snapshot)
    return snapshot, {entry.name: entry for entry in base.resolve_nodes(snapshot, {})}


def _async_driver(module):
    from hamilton import base
    from hamilton.async_driver import AsyncDriver

    return AsyncDriver({}, module, result_builder=base.DictResult())


def test_pinned_baseline_missing_async_identity_return_annotation(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step
def increment(value: int) -> int:
    return value + 1
@pipe_output(step(increment))
async def result() -> int:
    return 1
""")
    from hamilton.function_modifiers import base

    with pytest.raises(ValueError, match="Missing type hint for return value"):
        base.resolve_nodes(module.result, {})


def test_correction_does_not_admit_pipeline_decorators_to_the_frontend(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step
def increment(value: int) -> int:
    return value + 1
@pipe_output(step(increment))
async def result() -> int:
    return 1
""")

    with pytest.raises(ValueError, match="unsupported Hamilton decorator pipe_output"):
        Driver(module)


@pytest.mark.asyncio
async def test_correction_preserves_generated_shape_and_executes_sync_and_async_steps(module_factory):
    calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
async def increment_async(value: int) -> int:
    calls.append(("async", value))
    await asyncio.sleep(0)
    return value + 1
def double(value: int) -> int:
    calls.append(("sync", value))
    return value * 2
@pipe_output(step(double), step(increment_async), namespace="post")
async def result() -> int:
    calls.append(("producer",))
    return 2
""",
        asyncio=asyncio,
        calls=calls,
    )

    snapshot, nodes = _corrected_nodes(module.result)

    assert list(nodes) == ["result.raw", "post.with_double", "post.with_increment_async", "result"]
    assert [entry.type for entry in nodes.values()] == [int, int, int, int]
    assert [tuple(entry.input_types) for entry in nodes.values()] == [
        (),
        ("result.raw",),
        ("post.with_double",),
        ("post.with_increment_async",),
    ]
    assert inspect.iscoroutinefunction(nodes["result.raw"].callable)
    assert not inspect.iscoroutinefunction(nodes["post.with_double"].callable)
    assert inspect.iscoroutinefunction(nodes["post.with_increment_async"].callable)
    assert not inspect.iscoroutinefunction(nodes["result"].callable)

    module.result = snapshot
    assert await _async_driver(module).execute(["result"]) == {"result": 5}
    assert calls == [("producer",), ("sync", 2), ("async", 4)]


@pytest.mark.asyncio
async def test_correction_preserves_pipeline_step_exception_identity(module_factory):
    failure = RuntimeError("pipeline step failed")
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
def fail(value: int) -> int:
    raise failure
@pipe_output(step(fail))
async def result() -> int:
    return 1
""",
        failure=failure,
    )
    snapshot, _ = _corrected_nodes(module.result)
    module.result = snapshot

    with pytest.raises(RuntimeError) as info:
        await _async_driver(module).execute(["result"])
    assert info.value is failure


@pytest.mark.asyncio
async def test_correction_preserves_pipeline_cancellation(module_factory):
    started = asyncio.Event()
    wait_forever = asyncio.Event()
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
def increment(value: int) -> int:
    return value + 1
@pipe_output(step(increment))
async def result() -> int:
    started.set()
    await wait_forever.wait()
    return 1
""",
        started=started,
        wait_forever=wait_forever,
    )
    snapshot, _ = _corrected_nodes(module.result)
    module.result = snapshot

    running = asyncio.create_task(_async_driver(module).execute(["result"]))
    await started.wait()
    running.cancel("cancel corrected pipeline")
    with pytest.raises(asyncio.CancelledError, match="cancel corrected pipeline"):
        await running


def test_correction_is_idempotent_and_does_not_mutate_original_declaration(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step
def increment(value: int) -> int:
    return value + 1
@pipe_output(step(increment))
async def result() -> int:
    return 1
""")
    from hamilton.function_modifiers import base

    original_modifier = module.result.transform[0]
    original_state = dict(original_modifier.__dict__)
    snapshot = _copy_function(module.result)
    snapshot_modifier = snapshot.transform[0]

    correct_copied_async_output_pipelines(snapshot)
    corrected_method = snapshot_modifier.transform_node
    correct_copied_async_output_pipelines(snapshot)

    assert snapshot_modifier is not original_modifier
    assert snapshot_modifier.transform_node is corrected_method
    assert original_modifier.__dict__ == original_state
    with pytest.raises(ValueError, match="Missing type hint for return value"):
        base.resolve_nodes(module.result, {})
    assert {entry.name for entry in base.resolve_nodes(snapshot, {})} == {
        "result.raw",
        "result.with_increment",
        "result",
    }


@pytest.mark.parametrize("version_source", ["distribution", "imported"])
def test_correction_fails_closed_outside_the_pinned_hamilton_version(
    module_factory, monkeypatch, version_source
):
    from sdax_hamilton import _hamilton_pipeline

    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step
def increment(value: int) -> int:
    return value + 1
@pipe_output(step(increment))
async def result() -> int:
    return 1
""")
    snapshot = _copy_function(module.result)
    if version_source == "distribution":
        monkeypatch.setattr(_hamilton_pipeline.metadata, "version", lambda _: "1.91.0")
    else:
        monkeypatch.setattr(_hamilton_pipeline.hamilton, "__version__", (1, 91, 0))

    with pytest.raises(RuntimeError, match="requires apache-hamilton==1.90.0"):
        correct_copied_async_output_pipelines(snapshot)
    assert "__sdax_hamilton_async_output_pipeline_corrected__" not in snapshot.transform[0].__dict__
