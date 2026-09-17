"""Policy boundaries: callback effects and validation are separate."""

import asyncio

import pytest

from sdax_hamilton import Acquisition, Driver, execution, shutdown
from sdax_hamilton.declarations import Policy


class World:
    def __init__(self):
        self.attempts = 0
        self.events = []


class Handle:
    pass


def leaves(exc):
    if isinstance(exc, BaseExceptionGroup):
        return [leaf for child in exc.exceptions for leaf in leaves(child)]
    return [exc]


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


@pytest.mark.asyncio
async def test_timeout_retry_drains_attempt_before_next(make_module):
    mod = make_module("""
@execution(timeout=0.02, retries=1, initial_delay=0, retryable_exceptions=(TimeoutError,))
async def result(world: World) -> int:
    world.attempts += 1
    attempt = world.attempts
    world.events.append(f'start-{attempt}')
    try:
        if attempt == 1:
            await asyncio.sleep(10)
        return 42
    finally:
        world.events.append(f'stop-{attempt}')
""")
    world = World()
    assert await Driver(mod).prepare(["result"]).execute(inputs={"world": world}) == {"result": 42}
    assert world.events == ["start-1", "stop-1", "start-2", "stop-2"]


@pytest.mark.asyncio
async def test_output_validation_does_not_retry_side_effect(make_module):
    mod = make_module("""
@execution(retries=2, initial_delay=0, retryable_exceptions=(Exception,))
def result(world: World) -> int:
    world.attempts += 1
    return 'wrong'
""")
    world = World()
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute(inputs={"world": world})
    assert world.attempts == 1
    assert any(isinstance(e, TypeError) for e in leaves(info.value))


def test_acquisition_retry_rejected(make_module):
    mod = make_module("""
@execution(retries=1)
def owner() -> Handle:
    raise AssertionError('Must not run')
@shutdown(of=owner)
def close(state: Acquisition[Handle]) -> None:
    pass
""")
    with pytest.raises(ValueError):
        Driver(mod).prepare(["owner"])


@pytest.mark.asyncio
async def test_cleanup_validation_never_replays_cleanup(make_module):
    calls = []
    mod = make_module(
        """
def owner() -> int:
    return 1
@shutdown(of=owner, retries=1, initial_delay=0, retryable_exceptions=(TypeError,))
def close(state: Acquisition[int]) -> None:
    calls.append('release')
    return 'wrong'
def result(owner: int) -> int:
    return owner
""",
        calls=calls,
    )
    with pytest.raises(BaseExceptionGroup):
        await Driver(mod).prepare(["result"]).execute()
    assert calls == ["release"]


@pytest.mark.parametrize(
    "options",
    [
        {"retries": 1.5},
        {"retries": True},
        {"retries": -1},
        {"timeout": float("nan")},
        {"timeout": 0},
        {"timeout": -1},
        {"initial_delay": float("inf")},
        {"initial_delay": -1},
        {"backoff_factor": 0},
        {"retryable_exceptions": (BaseException,)},
        {"retryable_exceptions": (asyncio.CancelledError,)},
        {"retryable_exceptions": ("not a class",)},
        {"retryable_exceptions": ()},
    ],
)
def test_policy_validation(options):
    with pytest.raises(ValueError):
        Policy(**options)


def test_policy_defaults_and_immutability():
    policy = Policy()
    assert policy.timeout is None and policy.retries == 0
    assert policy.initial_delay == 1.0 and policy.backoff_factor == 2.0
    with pytest.raises((AttributeError, TypeError)):
        policy.retries = 4


@pytest.mark.asyncio
async def test_default_retry_exceptions_include_sdax_retryable(make_module):
    from sdax import RetryableException

    for error in (
        TimeoutError("timeout"),
        ConnectionError("connection"),
        RetryableException("retryable"),
    ):
        calls = []
        mod = make_module(
            """
@execution(retries=1, initial_delay=0)
def result() -> int:
    calls.append('run')
    if len(calls) == 1:
        raise error
    return 7
""",
            calls=calls,
            error=error,
        )
        assert await Driver(mod).prepare(["result"]).execute() == {"result": 7}
        assert calls == ["run", "run"]


@pytest.mark.asyncio
async def test_ordinary_value_error_is_not_retryable_by_default(make_module):
    error = ValueError("not retryable")
    calls = []
    mod = make_module(
        """
@execution(retries=2, initial_delay=0)
def result() -> int:
    calls.append('run')
    raise error
""",
        calls=calls,
        error=error,
    )
    with pytest.raises(BaseExceptionGroup) as info:
        await Driver(mod).prepare(["result"]).execute()
    assert calls == ["run"] and error in leaves(info.value)


@pytest.mark.asyncio
async def test_output_checks_can_be_disabled_without_repeating_callback(make_module):
    calls = []
    mod = make_module(
        """
def result() -> int:
    calls.append('run')
    return 'unchecked'
""",
        calls=calls,
    )
    assert await Driver(mod).prepare(["result"], check_outputs=False).execute() == {
        "result": "unchecked"
    }
    assert calls == ["run"]


def test_decorators_preserve_direct_call_and_identity():
    def resource() -> int:
        return 4

    assert execution(timeout=1)(resource) is resource
    assert resource() == 4

    def close(state: Acquisition[int]) -> None:
        pass

    assert shutdown(of=resource)(close) is close
    assert close.__name__ == "close"


@pytest.mark.asyncio
async def test_execution_target_collection_is_captured_at_decoration(make_module):
    from hamilton.function_modifiers import parameterize, value

    targets = ["left"]
    calls = []
    module = make_module(
        """
@execution(target_=targets, retries=1, initial_delay=0)
@parameterize(left={'number': value(1)}, right={'number': value(2)})
def result(number: int) -> int:
    calls.append(number)
    if calls.count(number) == 1:
        raise ConnectionError('first attempt fails')
    return number
""",
        targets=targets,
        calls=calls,
        parameterize=parameterize,
        value=value,
    )
    targets[:] = ["right"]
    assert await Driver(module).prepare(["left"]).execute() == {"left": 1}
    assert calls == [1, 1]
