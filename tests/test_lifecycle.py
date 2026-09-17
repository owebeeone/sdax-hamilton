"""Lifecycle guarantees through the public Hamilton frontend."""

import asyncio

import pytest

from sdax_hamilton import Acquisition, Driver, PreparedPlan, execution, failures, shutdown


class World:
    def __init__(self, seed=1, mode="success"):
        self.seed = seed
        self.mode = mode
        self.events = []
        self.slow_started = asyncio.Event()
        self.waiter = asyncio.Event()
        self.release_started = asyncio.Event()
        self.release_gate = None
        self.cleanup_error = None
        self.user_error = ValueError("consumer failed")
        self.attempts = 0
        self.states = []


class Handle:
    def __init__(self, world, parent=None):
        self.world = world
        self.parent = parent
        self.live = True


def leaves(exc):
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in leaves(child)]
    return [exc]


LIFECYCLE = """
async def parent(world: World) -> Handle:
    world.events.append('acquire-parent')
    await asyncio.sleep(0)
    return Handle(world)

@shutdown(of=parent)
async def close_parent(state: Acquisition[Handle]) -> None:
    if state.has_value:
        handle = state.value
        handle.live = False
        handle.world.events.append('release-parent')

async def child(parent: Handle) -> Handle:
    assert parent.live
    parent.world.events.append('acquire-child')
    return Handle(parent.world, parent)

@shutdown(of=child)
async def close_child(state: Acquisition[Handle]) -> None:
    if state.has_value:
        handle = state.value
        assert handle.parent.live
        world = handle.world
        world.release_started.set()
        if world.release_gate is not None:
            await world.release_gate.wait()
        handle.live = False
        world.events.append('release-child')
        if world.cleanup_error is not None:
            raise world.cleanup_error

async def slow(child: Handle) -> int:
    world = child.world
    world.events.append('slow-start')
    world.slow_started.set()
    try:
        if world.mode != 'success':
            await world.waiter.wait()
        else:
            await asyncio.sleep(0)
        return world.seed
    finally:
        assert child.live and child.parent.live
        world.events.append('slow-stop')

async def fast(child: Handle) -> int:
    world = child.world
    await world.slow_started.wait()
    if world.mode == 'failure':
        raise world.user_error
    return world.seed * 2

def result(slow: int, fast: int) -> int:
    return slow + fast
"""


@pytest.fixture
def make_module(module_factory):
    def make(source_text, **bindings):
        return module_factory(
            source_text,
            World=World,
            Handle=Handle,
            Acquisition=Acquisition,
            execution=execution,
            shutdown=shutdown,
            asyncio=asyncio,
            **bindings,
        )

    return make


def lifecycle_plan(make_module, outputs=("result",)):
    return Driver(make_module(LIFECYCLE)).prepare(outputs)


@pytest.mark.asyncio
async def test_reuse_and_concurrent_context_isolation(make_module, monkeypatch):
    from sdax import AsyncDagTaskProcessor

    original = AsyncDagTaskProcessor.builder
    builds = []

    def counted():
        builds.append(1)
        return original()

    monkeypatch.setattr(AsyncDagTaskProcessor, "builder", staticmethod(counted))
    plan = lifecycle_plan(make_module)
    assert isinstance(plan, PreparedPlan)
    worlds = [World(seed=i) for i in range(12)]
    results = await asyncio.gather(*(plan.execute(inputs={"world": w}) for w in worlds))
    assert results == [{"result": i * 3} for i in range(12)]
    assert await plan.execute(inputs={"world": World(20)}) == {"result": 60}
    assert len(builds) == 1
    for w in worlds:
        assert w.events.count("release-parent") == w.events.count("release-child") == 1
        assert (
            w.events.index("slow-stop")
            < w.events.index("release-child")
            < w.events.index("release-parent")
        )


@pytest.mark.asyncio
async def test_consumer_failure_drains_sibling_and_preserves_cleanup_fault(make_module):
    world = World(mode="failure")
    world.cleanup_error = RuntimeError("child release failed")
    with pytest.raises(BaseExceptionGroup) as info:
        await lifecycle_plan(make_module).execute(inputs={"world": world})
    assert world.user_error in leaves(info.value)
    assert world.cleanup_error in leaves(info.value)
    assert (
        world.events.index("slow-stop")
        < world.events.index("release-child")
        < world.events.index("release-parent")
    )


@pytest.mark.asyncio
async def test_cancellation_during_consumer_then_again_during_release(make_module):
    world = World(mode="cancel")
    world.release_gate = asyncio.Event()
    world.cleanup_error = RuntimeError("release after cancellation")
    job = asyncio.create_task(lifecycle_plan(make_module).execute(inputs={"world": world}))
    await asyncio.wait_for(world.slow_started.wait(), 1)
    job.cancel("first cancellation")
    await asyncio.wait_for(world.release_started.wait(), 1)
    job.cancel("second cancellation")
    await asyncio.sleep(0)
    assert not job.done()
    world.release_gate.set()
    with pytest.raises(asyncio.CancelledError) as info:
        await asyncio.wait_for(job, 1)
    assert "first cancellation" in str(info.value)
    assert any(world.cleanup_error in leaves(e) for e in failures(info.value))
    assert world.events.count("release-child") == world.events.count("release-parent") == 1
    assert (
        world.events.index("slow-stop")
        < world.events.index("release-child")
        < world.events.index("release-parent")
    )


@pytest.mark.asyncio
async def test_scope_body_error_identity_and_release_diagnostics(make_module):
    world = World()
    world.cleanup_error = RuntimeError("cleanup fault")
    body_error = LookupError("scope fault")
    with pytest.raises(LookupError) as info:
        async with lifecycle_plan(make_module, ["child"]).open(inputs={"world": world}) as values:
            assert values["child"].live and values["child"].parent.live
            raise body_error
    assert info.value is body_error
    assert any(world.cleanup_error in leaves(e) for e in failures(body_error))
    assert world.events[-2:] == ["release-child", "release-parent"]


@pytest.mark.asyncio
async def test_resource_output_requires_scope(make_module):
    world = World()
    plan = lifecycle_plan(make_module, ["child"])
    with pytest.raises(ValueError, match="open"):
        await plan.execute(inputs={"world": world})
    assert not world.events
    async with plan.open(inputs={"world": world}) as values:
        handle = values["child"]
        assert handle.live
    assert not handle.live and not handle.parent.live


@pytest.mark.parametrize("replacement", ["config", "override"])
def test_owned_replacement_is_rejected(make_module, replacement):
    world = World()
    mod = make_module(LIFECYCLE)
    with pytest.raises((ValueError, TypeError)):
        driver = Driver(mod, config={"parent": Handle(world)} if replacement == "config" else {})
        driver.prepare(["result"], override_nodes=["parent"] if replacement == "override" else [])
    assert not world.events


@pytest.mark.asyncio
async def test_input_shapes_and_types_before_acquisition(make_module):
    plan = lifecycle_plan(make_module)
    world = World()
    for inputs in ({}, {"world": None}, {"world": world, "extra": 1}):
        with pytest.raises((ValueError, TypeError)):
            await plan.execute(inputs=inputs)
    assert not world.events


@pytest.mark.asyncio
async def test_invalid_resource_retained_without_false_typed_access(make_module):
    returned = object()
    states = []
    mod = make_module(
        """
def owner() -> Handle:
    return returned
@shutdown(of=owner)
def close(state: Acquisition[Handle]) -> None:
    states.append(state)
    assert state.has_value and not state.is_valid
    assert state.raw_value is returned
    try:
        state.value
    except TypeError:
        return
    raise AssertionError('Invalid typed access was allowed')
def result(owner: Handle) -> int:
    raise AssertionError('Consumer must not run')
""",
        returned=returned,
        states=states,
    )
    with pytest.raises(BaseExceptionGroup):
        await Driver(mod).prepare(["result"]).execute()
    assert len(states) == 1 and states[0].raw_value is returned


@pytest.mark.parametrize("mode", ["none", "fail"])
@pytest.mark.asyncio
async def test_published_none_distinct_from_absent_acquisition(make_module, mode):
    states = []
    mod = make_module(
        """
def owner() -> None:
    if mode == 'fail':
        raise ValueError('before publication')
    return None
@shutdown(of=owner)
def close(state: Acquisition[None]) -> None:
    states.append(state)
def result(owner: None) -> int:
    return 1
""",
        mode=mode,
        states=states,
    )
    plan = Driver(mod).prepare(["result"])
    if mode == "fail":
        with pytest.raises(BaseExceptionGroup):
            await plan.execute()
    else:
        assert await plan.execute() == {"result": 1}
    assert len(states) == 1 and states[0].has_value == (mode == "none")
    if mode == "none":
        assert states[0].value is None


@pytest.mark.asyncio
async def test_optional_shape_and_override_pruning(make_module):
    mod = make_module("""
def costly() -> int:
    raise AssertionError('Overridden producer executed')
def result(costly: int, extra: int = 5) -> int:
    return costly + extra
""")
    driver = Driver(mod)
    plan = driver.prepare(["result"], override_nodes=["costly"])
    assert await plan.execute(overrides={"costly": 7}) == {"result": 12}
    with pytest.raises(ValueError):
        await plan.execute(inputs={"extra": 3}, overrides={"costly": 7})
    explicit = driver.prepare(["result"], override_nodes=["costly"], optional_inputs=["extra"])
    assert await explicit.execute(inputs={"extra": 3}, overrides={"costly": 7}) == {"result": 10}


@pytest.mark.asyncio
async def test_explicit_validation_node_preserves_acquisition_owner(make_module):
    world = World()
    mod = make_module(
        LIFECYCLE
        + """
def validated(child: Handle) -> Handle:
    raise ValueError('validation rejected resource')
"""
    )
    with pytest.raises(BaseExceptionGroup):
        await Driver(mod).prepare(["validated"]).execute(inputs={"world": world})
    assert world.events == ["acquire-parent", "acquire-child", "release-child", "release-parent"]


@pytest.mark.asyncio
async def test_callback_originated_cleanup_cancellation_is_not_success(make_module):
    cancelled = asyncio.CancelledError("release cancelled itself")
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner)
async def close(state: Acquisition[int]) -> None:
    raise cancelled
def result(owner: int) -> int:
    return owner
""",
        cancelled=cancelled,
    )
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute()
    assert cancelled in leaves(info.value)


@pytest.mark.asyncio
async def test_cancellation_during_body_error_cleanup_takes_priority(make_module):
    world = World()
    world.release_gate = asyncio.Event()
    body_error = ValueError("body failure before cancellation")

    async def use():
        async with lifecycle_plan(make_module, ["child"]).open(inputs={"world": world}):
            raise body_error

    job = asyncio.create_task(use())
    await asyncio.wait_for(world.release_started.wait(), 1)
    job.cancel("cancel during body cleanup")
    await asyncio.sleep(0)
    world.release_gate.set()
    with pytest.raises(asyncio.CancelledError) as info:
        await job
    assert body_error in failures(info.value)
    assert world.events[-2:] == ["release-child", "release-parent"]


@pytest.mark.asyncio
async def test_release_timeout_preserves_parent_release(make_module):
    mod = make_module(LIFECYCLE.replace("@shutdown(of=child)", "@shutdown(of=child, timeout=0.02)"))
    world = World()
    world.release_gate = asyncio.Event()
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute(inputs={"world": world})
    assert world.events[-1] == "release-parent"
    assert any(isinstance(e, TimeoutError) for e in leaves(info.value))


@pytest.mark.asyncio
async def test_all_consumers_contribute_input_contract(make_module):
    calls = []
    mod = make_module(
        """
def strict(x: int = 1) -> int:
    calls.append('strict')
    return 1
def wide(x: int | str) -> int:
    calls.append('wide')
    return 2
def result(strict: int, wide: int) -> int:
    return strict + wide
""",
        calls=calls,
    )
    plan = Driver(mod).prepare(["result"])
    with pytest.raises(TypeError):
        await plan.execute(inputs={"x": "bad"})
    assert calls == []


@pytest.mark.asyncio
async def test_forward_self_cancellation_preserves_original_error(make_module):
    cancelled = asyncio.CancelledError("forward cancelled itself")
    calls = []
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    calls.append('close')
async def result(owner: int) -> int:
    raise cancelled
""",
        cancelled=cancelled,
        calls=calls,
    )
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute()
    assert cancelled in leaves(info.value)
    assert not any(isinstance(exc, KeyError) for exc in leaves(info.value))
    assert calls == ["close"]


@pytest.mark.asyncio
async def test_forward_self_cancellation_survives_cleanup_failure(make_module):
    cancelled = asyncio.CancelledError("forward cancelled itself")
    cleanup_error = RuntimeError("release failed")
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    raise cleanup_error
async def result(owner: int) -> int:
    raise cancelled
""",
        cancelled=cancelled,
        cleanup_error=cleanup_error,
    )
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute()
    assert cancelled in leaves(info.value)
    assert cleanup_error in leaves(info.value)


@pytest.mark.asyncio
async def test_simultaneous_forward_failure_preserves_caller_cancellation(make_module):
    error = ValueError("forward failed concurrently")
    calls = []
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    calls.append('close')
async def result(owner: int) -> int:
    caller.cancel('external cancellation')
    raise error
""",
        caller=None,
        error=error,
        calls=calls,
    )

    async def use():
        mod.caller = asyncio.current_task()
        await Driver(mod).prepare(["result"]).execute()

    job = asyncio.create_task(use())
    with pytest.raises(asyncio.CancelledError, match="external cancellation") as info:
        await job
    assert any(error in leaves(exc) for exc in failures(info.value))
    assert calls == ["close"]


@pytest.mark.asyncio
async def test_preexisting_cancellation_count_does_not_cancel_new_invocation(make_module):
    mod = make_module("""
def result() -> int:
    return 7
""")

    async def use():
        task = asyncio.current_task()
        task.cancel("earlier handled cancellation")
        try:
            await asyncio.sleep(0)
        except asyncio.CancelledError:
            pass
        before = task.cancelling()
        assert before == 1
        assert await Driver(mod).prepare(["result"]).execute() == {"result": 7}
        assert task.cancelling() == before

    await asyncio.create_task(use())


@pytest.mark.asyncio
async def test_repeated_caller_cancellation_joins_forward_drain_before_release(make_module):
    started, draining, finish = asyncio.Event(), asyncio.Event(), asyncio.Event()
    events = []
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    events.append('release')
async def result(owner: int) -> int:
    started.set()
    try:
        await asyncio.Event().wait()
    finally:
        draining.set()
        await finish.wait()
        events.append('forward-drained')
    return owner
""",
        started=started,
        draining=draining,
        finish=finish,
        events=events,
    )
    job = asyncio.create_task(Driver(mod).prepare(["result"]).execute())
    await asyncio.wait_for(started.wait(), 1)
    job.cancel("first cancellation")
    await asyncio.wait_for(draining.wait(), 1)
    job.cancel("second cancellation")
    await asyncio.sleep(0)
    assert not job.done() and not events
    finish.set()
    with pytest.raises(asyncio.CancelledError, match="first cancellation"):
        await asyncio.wait_for(job, 1)
    assert events == ["forward-drained", "release"]


@pytest.mark.asyncio
async def test_independent_cleanup_faults_are_both_reported(make_module):
    left_error, right_error = RuntimeError("left"), LookupError("right")
    both_releasing = asyncio.Event()
    calls = []
    mod = make_module(
        """
def left() -> int:
    return 1
def right() -> int:
    return 2
@shutdown(of=left)
async def close_left(state: Acquisition[int]) -> None:
    calls.append('left')
    if len(calls) == 2:
        both_releasing.set()
    await both_releasing.wait()
    raise left_error
@shutdown(of=right)
async def close_right(state: Acquisition[int]) -> None:
    calls.append('right')
    if len(calls) == 2:
        both_releasing.set()
    await both_releasing.wait()
    raise right_error
def result(left: int, right: int) -> int:
    return left + right
""",
        calls=calls,
        both_releasing=both_releasing,
        left_error=left_error,
        right_error=right_error,
    )
    with pytest.raises(BaseExceptionGroup) as info:
        await asyncio.wait_for(Driver(mod).prepare(["result"]).execute(), 2)
    assert left_error in leaves(info.value) and right_error in leaves(info.value)
    assert sorted(calls) == ["left", "right"]


def test_prepared_plan_public_shape_is_read_only(make_module):
    plan = lifecycle_plan(make_module)
    assert tuple(plan.outputs) == ("result",)
    assert set(plan.required_inputs) == {"world"}
    assert set(plan.override_nodes) == set()
    for attribute in ("outputs", "required_inputs", "override_nodes"):
        with pytest.raises((AttributeError, TypeError)):
            setattr(plan, attribute, ())


def test_failure_helper_for_unrelated_exception():
    assert failures(ValueError("ordinary exception")) == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", ["config", "override"])
async def test_fully_replaced_output_has_no_active_callbacks(make_module, replacement):
    calls = []
    module = make_module(
        """
def expensive(seed: int) -> int:
    calls.append('expensive')
    raise AssertionError('Replaced producer must not execute')
""",
        calls=calls,
    )
    if replacement == "config":
        plan = Driver(module, config={"expensive": 11}).prepare(["expensive"])
        assert await plan.execute() == {"expensive": 11}
    else:
        plan = Driver(module).prepare(["expensive"], override_nodes=["expensive"])
        assert await plan.execute(overrides={"expensive": 12}) == {"expensive": 12}
    assert not plan.required_inputs
    assert calls == []


@pytest.mark.parametrize("outputs", ["result", ["result", "result"]])
def test_malformed_output_collections_rejected(make_module, outputs):
    module = make_module("""
def result() -> int:
    return 1
""")
    with pytest.raises((TypeError, ValueError), match="final_vars"):
        Driver(module).prepare(outputs)
