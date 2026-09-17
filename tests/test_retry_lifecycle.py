"""Retries preserve ownership and retain failures without repeating acquisition."""

import pytest

from sdax_hamilton import Driver


def leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in leaves(child)]
    return [error]


@pytest.mark.asyncio
async def test_exhausted_consumer_retries_release_resource_once(module_factory):
    events = []
    error = ConnectionError("consumer never recovers")
    module = module_factory(
        """
from sdax_hamilton import Acquisition, execution, shutdown

def resource() -> int:
    events.append('acquire')
    return 1

@shutdown(of=resource)
def close(state: Acquisition[int]) -> None:
    assert state.value == 1
    events.append('release')

@execution(retries=2, initial_delay=0)
def result(resource: int) -> int:
    events.append('attempt')
    raise error
""",
        events=events,
        error=error,
    )
    with pytest.raises(BaseExceptionGroup) as result:
        await Driver(module).prepare(["result"]).execute()
    assert error in leaves(result.value)
    assert events == ["acquire", "attempt", "attempt", "attempt", "release"]


@pytest.mark.asyncio
@pytest.mark.parametrize("succeeds", [True, False])
async def test_explicit_shutdown_retries_finish_before_parent_shutdown(module_factory, succeeds):
    events = []
    error = ConnectionError("release fault")
    module = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def parent() -> int:
    return 1

@shutdown(of=parent)
def close_parent(state: Acquisition[int]) -> None:
    events.append('parent-release')

def child(parent: int) -> int:
    return parent + 1

@shutdown(of=child, retries=1, initial_delay=0)
def close_child(state: Acquisition[int]) -> None:
    events.append('child-release')
    if not succeeds or events.count('child-release') == 1:
        raise error

def result(child: int) -> int:
    return child
""",
        events=events,
        error=error,
        succeeds=succeeds,
    )
    plan = Driver(module).prepare(["result"])
    if succeeds:
        assert await plan.execute() == {"result": 2}
    else:
        with pytest.raises(BaseExceptionGroup) as result:
            await plan.execute()
        assert error in leaves(result.value)
    assert events == ["child-release", "child-release", "parent-release"]
