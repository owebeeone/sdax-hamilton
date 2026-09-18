"""V x D qualification for exact optional validators returned by a resolver."""

import os

import pytest
from hamilton import driver as hamilton_driver
from hamilton import settings

from sdax_hamilton import Driver

_PROFILE_VARIABLE = "SDAX_HAMILTON_TEST_PROFILE"
_CONFIGURATION = {settings.ENABLE_POWER_USER_MODE: True}




def require_profile(expected):
    if os.environ.get(_PROFILE_VARIABLE) != expected:
        pytest.skip(f"requires {_PROFILE_VARIABLE}={expected}")


@pytest.mark.asyncio
async def test_delayed_pydantic_validator_matches_stock_and_preserves_identity(
    module_factory,
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    source = """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config
from hamilton.plugins import h_pydantic

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return h_pydantic.check_output(importance="fail")

@resolve_from_config(decorate_with=decorate_with)
def result() -> Item:
    return payload
"""
    for payload in (Item(count=1), {"count": 2}):
        resolver_calls = []
        module = module_factory(
            source,
            Item=Item,
            payload=payload,
            resolver_calls=resolver_calls,
        )
        oracle = (
            hamilton_driver.Builder()
            .with_modules(module)
            .with_config(_CONFIGURATION)
            .build()
        )
        assert oracle.execute(["result"])["result"] is payload
        assert resolver_calls == ["resolve"]

        resolver_calls.clear()
        result = await Driver(module, config=_CONFIGURATION).prepare(["result"]).execute()
        assert result["result"] is payload
        assert resolver_calls == ["resolve"]


@pytest.mark.asyncio
async def test_delayed_pandera_validator_matches_stock_and_preserves_identity(
    module_factory,
):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    resolver_calls = []
    frame = pandas.DataFrame({"count": [1]})
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config
from hamilton.plugins import h_pandera

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return h_pandera.check_output(importance="fail")

@resolve_from_config(decorate_with=decorate_with)
def result() -> FrameType:
    return frame
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        frame=frame,
        resolver_calls=resolver_calls,
    )
    oracle = (
        hamilton_driver.Builder()
        .with_modules(module)
        .with_config(_CONFIGURATION)
        .build()
    )
    assert oracle.execute(["result"])["result"] is frame
    assert resolver_calls == ["resolve"]

    resolver_calls.clear()
    result = await Driver(module, config=_CONFIGURATION).prepare(["result"]).execute()
    assert result["result"] is frame
    assert resolver_calls == ["resolve"]


def test_delayed_pandera_parameter_contract_is_not_deferred(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    resolver_calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config
from hamilton.plugins import h_pandera

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return h_pandera.check_output(importance="fail")

@resolve_from_config(decorate_with=decorate_with)
def result(frame: FrameType) -> FrameType:
    return frame
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        frame=pandas.DataFrame({"count": [1]}),
        resolver_calls=resolver_calls,
    )

    with pytest.raises(TypeError, match="Unsupported annotation"):
        Driver(module, config=_CONFIGURATION)
    assert resolver_calls == []


def test_delayed_pandera_invalid_default_fails_before_resolution(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    resolver_calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config
from hamilton.plugins import h_pandera

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return h_pandera.check_output(importance="fail")

@resolve_from_config(decorate_with=decorate_with)
def result(count: int = "invalid") -> FrameType:
    return frame
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        frame=pandas.DataFrame({"count": [1]}),
        resolver_calls=resolver_calls,
    )

    with pytest.raises(TypeError, match="result.count: invalid default"):
        Driver(module, config=_CONFIGURATION)
    assert resolver_calls == []


def test_delayed_nonvalidator_generic_return_rejected_after_one_resolution(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    resolver_calls = []
    events = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, tag

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return tag(stage="delayed")

@resolve_from_config(decorate_with=decorate_with)
def result() -> FrameType:
    events.append("result")
    return frame
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        events=events,
        frame=pandas.DataFrame({"count": [1]}),
        resolver_calls=resolver_calls,
    )

    with pytest.raises(TypeError, match="Unsupported annotation"):
        Driver(module, config=_CONFIGURATION)
    assert resolver_calls == ["resolve"]
    assert events == []
