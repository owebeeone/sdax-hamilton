"""Pinned optional-validator behavior and explicit future frontend gates."""

import logging
import os
from functools import partial
from typing import Any, get_args, get_origin

import pytest
from hamilton import driver as hamilton_driver
from hamilton import node
from hamilton.data_quality.base import DataValidationError

from sdax_hamilton import Driver, hamilton_compat
from sdax_hamilton import driver as driver_module
from sdax_hamilton._hamilton_validation import (
    correct_validation_gate,
    correct_validation_representation,
    normalize_validation_annotation,
)

_PROFILE_VARIABLE = "SDAX_HAMILTON_TEST_PROFILE"


@pytest.fixture(autouse=True)
def _provisional_v_admission(monkeypatch):
    """Exercise production profile dispatch while the public QC gate is closed."""
    profile = os.environ.get(_PROFILE_VARIABLE)
    if profile == "pydantic":
        from hamilton.plugins.h_pydantic import check_output
    elif profile == "pandera":
        from hamilton.plugins.h_pandera import check_output
    else:
        return
    monkeypatch.setattr(
        driver_module,
        "compile_modules",
        partial(
            hamilton_compat.compile_modules,
            _supported=(*hamilton_compat._SUPPORTED, check_output),
        ),
    )


def require_profile(expected):
    selected = os.environ.get(_PROFILE_VARIABLE)
    if selected != expected:
        pytest.skip(f"requires {_PROFILE_VARIABLE}={expected}")


def leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for nested in error.exceptions for leaf in leaves(nested)]
    return [error]


def test_pydantic_generated_representation_is_model_or_dict():
    require_profile("pydantic")
    import pydantic
    from hamilton.plugins import h_pydantic

    class Item(pydantic.BaseModel):
        count: int

    def result() -> Item:
        return Item(count=1)

    generated = h_pydantic.check_output(importance="fail").transform_node(
        node.Node.from_fn(result), {}, result
    )
    corrected = correct_validation_representation(
        correct_validation_gate(generated), "pydantic"
    )
    evidence, gate, raw = corrected

    model_type, dictionary_type = get_args(raw.type)
    assert model_type is Item
    assert get_origin(dictionary_type) is dict
    assert get_args(dictionary_type) == (str, Any)
    assert gate.type == raw.type
    assert evidence.input_types[raw.name][0] == raw.type
    assert gate.input_types[raw.name][0] == raw.type


def test_pandera_generated_representation_is_concrete_pandas_dataframe():
    require_profile("pandera")
    import pandas
    import pandera
    from hamilton.plugins import h_pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    frame_type = pa_typing.DataFrame[FrameSchema]

    def result() -> frame_type:
        return pandas.DataFrame({"count": [1]})

    generated = h_pandera.check_output(importance="fail").transform_node(
        node.Node.from_fn(result), {}, result
    )
    corrected = correct_validation_representation(
        correct_validation_gate(generated), "pandera"
    )
    evidence, gate, raw = corrected

    assert normalize_validation_annotation(frame_type, "pandera") is pandas.DataFrame
    assert raw.type is pandas.DataFrame
    assert gate.type is pandas.DataFrame
    assert evidence.input_types[raw.name][0] is pandas.DataFrame
    assert gate.input_types[raw.name][0] is pandas.DataFrame


def test_upstream_pydantic_validator_preserves_model_and_valid_dict_representations(
    module_factory,
):
    require_profile("pydantic")
    import pydantic
    from hamilton.plugins import h_pydantic  # noqa: F401

    class Item(pydantic.BaseModel):
        count: int

    source = """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload
"""
    model = Item(count=1)
    valid_dict = {"count": 2}
    for payload in (model, valid_dict):
        module = module_factory(source, Item=Item, payload=payload)
        oracle = hamilton_driver.Builder().with_modules(module).build()
        assert oracle.execute(["result"])["result"] is payload


def test_upstream_pydantic_validator_is_strict_and_does_not_coerce_downstream(
    module_factory,
):
    require_profile("pydantic")
    import pydantic
    from hamilton.plugins import h_pydantic  # noqa: F401

    class Item(pydantic.BaseModel):
        count: int

    invalid = {"count": "1"}
    module = module_factory(
        """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload
""",
        Item=Item,
        payload=invalid,
    )
    oracle = hamilton_driver.Builder().with_modules(module).build()
    with pytest.raises(DataValidationError):
        oracle.execute(["result"])
    assert invalid == {"count": "1"}

    valid_dict = {"count": 1}
    downstream = module_factory(
        """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload

def consumer(result: Item) -> int:
    return result.count
""",
        Item=Item,
        payload=valid_dict,
    )
    downstream_oracle = hamilton_driver.Builder().with_modules(downstream).build()
    with pytest.raises(AttributeError):
        downstream_oracle.execute(["consumer"])
    assert valid_dict == {"count": 1}


@pytest.mark.asyncio
async def test_frontend_pydantic_preserves_valid_model_and_dict_identity(
    module_factory,
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    source = """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload
"""
    for payload in (Item(count=1), {"count": 2}):
        module = module_factory(source, Item=Item, payload=payload)
        result = await Driver(module).prepare(["result"]).execute()
        assert result["result"] is payload


@pytest.mark.asyncio
async def test_frontend_pydantic_owned_representation_releases_raw_identity_once(
    module_factory,
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    source = """
from typing import Any
from hamilton.plugins import h_pydantic
from sdax_hamilton import Acquisition, shutdown

Owned = Item | dict[str, Any]

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    events.append("acquire")
    return payload

@shutdown(of=result)
def close(state: Acquisition[Owned]) -> None:
    assert state.value is payload
    events.append("release")
"""
    for payload in (Item(count=1), {"count": 2}):
        events = []
        module = module_factory(source, Item=Item, events=events, payload=payload)
        plan = Driver(module).prepare(["result"])

        with pytest.raises(ValueError, match="open"):
            await plan.execute()
        assert events == []
        async with plan.open() as result:
            assert result["result"] is payload
            assert events == ["acquire"]
        assert events == ["acquire", "release"]


def test_frontend_pydantic_nominal_shutdown_rejects_possible_dict_before_effects(
    module_factory,
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    events = []
    module = module_factory(
        """
from hamilton.plugins import h_pydantic
from sdax_hamilton import Acquisition, shutdown

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    events.append("acquire")
    return {"count": 1}

@shutdown(of=result)
def close(state: Acquisition[Item]) -> None:
    events.append("release")
""",
        Item=Item,
        events=events,
    )

    with pytest.raises(TypeError, match="shutdown Acquisition type does not accept"):
        Driver(module)
    assert events == []


@pytest.mark.asyncio
async def test_frontend_pydantic_dict_cannot_reach_nominal_model_consumer(
    module_factory,
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    calls = []
    module = module_factory(
        """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload

def consumer(result: Item) -> int:
    calls.append("consumer")
    return result.count
""",
        Item=Item,
        calls=calls,
        payload={"count": 1},
    )
    with pytest.raises(ValueError, match="consumer is expecting result"):
        Driver(module)
    assert calls == []


@pytest.mark.asyncio
async def test_frontend_pydantic_failure_is_nonbypassable_and_data_minimal(
    module_factory, caplog
):
    require_profile("pydantic")
    import pydantic

    class Item(pydantic.BaseModel):
        count: int

    secret = "SENTINEL-PYDANTIC-VALIDATION"
    module = module_factory(
        """
from hamilton.plugins import h_pydantic

@h_pydantic.check_output(importance="fail")
def result() -> Item:
    return payload
""",
        Item=Item,
        payload={"count": secret},
    )
    driver = Driver(module)

    with pytest.raises(ValueError, match="internals cannot be selected"):
        driver.prepare(["result_raw"])
    with caplog.at_level(logging.WARNING), pytest.raises(BaseExceptionGroup) as error:
        await driver.prepare(["result"], check_outputs=False).execute()
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    rendered += f"\n{error.value}"
    assert any(isinstance(leaf, DataValidationError) for leaf in leaves(error.value))
    assert secret not in rendered


def test_upstream_pandera_validator_preserves_valid_frame_and_rejects_invalid_frame(
    module_factory,
):
    require_profile("pandera")
    import pandas
    import pandera
    from hamilton.plugins import h_pandera  # noqa: F401
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    source = """
from hamilton.plugins import h_pandera

@h_pandera.check_output(importance="fail")
def result() -> FrameType:
    return payload
"""
    frame_type = pa_typing.DataFrame[FrameSchema]
    valid = pandas.DataFrame({"count": [1]})
    valid_module = module_factory(source, FrameType=frame_type, payload=valid)
    valid_oracle = hamilton_driver.Builder().with_modules(valid_module).build()
    assert valid_oracle.execute(["result"])["result"] is valid

    invalid = pandas.DataFrame({"count": ["wrong"]})
    invalid_module = module_factory(source, FrameType=frame_type, payload=invalid)
    invalid_oracle = hamilton_driver.Builder().with_modules(invalid_module).build()
    with pytest.raises(DataValidationError):
        invalid_oracle.execute(["result"])


@pytest.mark.asyncio
async def test_frontend_pandera_valid_frame_preserves_identity(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    frame_type = pa_typing.DataFrame[FrameSchema]
    frame = pandas.DataFrame({"count": [1]})
    module = module_factory(
        """
from hamilton.plugins import h_pandera

@h_pandera.check_output(importance="fail")
def result() -> FrameType:
    return frame

def consumer(result: PandasDataFrame) -> PandasDataFrame:
    return result
""",
        FrameType=frame_type,
        PandasDataFrame=pandas.DataFrame,
        frame=frame,
    )

    result = await Driver(module).prepare(["consumer"]).execute()
    assert result["consumer"] is frame


def test_frontend_pandera_generic_downstream_remains_unsupported(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    calls = []
    module = module_factory(
        """
from hamilton.plugins import h_pandera

@h_pandera.check_output(importance="fail")
def result() -> FrameType:
    return frame

def consumer(result: FrameType) -> int:
    calls.append("consumer")
    return len(result)
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        calls=calls,
        frame=pandas.DataFrame({"count": [1]}),
    )

    with pytest.raises(TypeError, match="Unsupported annotation"):
        Driver(module)
    assert calls == []


@pytest.mark.asyncio
async def test_frontend_pandera_owned_frame_uses_concrete_shutdown_type(module_factory):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    source = """
from hamilton.plugins import h_pandera
from sdax_hamilton import Acquisition, shutdown

@h_pandera.check_output(importance="fail")
def result() -> FrameType:
    events.append("acquire")
    return frame

@shutdown(of=result)
def close(state: Acquisition[ShutdownType]) -> None:
    assert state.value is frame
    events.append("release")
"""
    frame_type = pa_typing.DataFrame[FrameSchema]
    frame = pandas.DataFrame({"count": [1]})
    events = []
    concrete = module_factory(
        source,
        FrameType=frame_type,
        ShutdownType=pandas.DataFrame,
        events=events,
        frame=frame,
    )
    plan = Driver(concrete).prepare(["result"])

    with pytest.raises(ValueError, match="open"):
        await plan.execute()
    assert events == []
    async with plan.open() as result:
        assert result["result"] is frame
        assert events == ["acquire"]
    assert events == ["acquire", "release"]

    generic_events = []
    generic = module_factory(
        source,
        FrameType=frame_type,
        ShutdownType=frame_type,
        events=generic_events,
        frame=frame,
    )
    with pytest.raises(TypeError, match="Unsupported annotation"):
        Driver(generic)
    assert generic_events == []


@pytest.mark.asyncio
async def test_frontend_pandera_failure_is_nonbypassable_and_data_minimal(
    module_factory, caplog
):
    require_profile("pandera")
    import pandas
    import pandera
    from pandera import typing as pa_typing

    class FrameSchema(pandera.DataFrameModel):
        count: int

    secret = "SENTINEL-PANDERA-VALIDATION"
    module = module_factory(
        """
from hamilton.plugins import h_pandera

@h_pandera.check_output(importance="fail")
def result() -> FrameType:
    return frame
""",
        FrameType=pa_typing.DataFrame[FrameSchema],
        frame=pandas.DataFrame({"count": [secret]}),
    )
    driver = Driver(module)

    with pytest.raises(ValueError, match="internals cannot be selected"):
        driver.prepare(["result_raw"])
    with caplog.at_level(logging.WARNING), pytest.raises(BaseExceptionGroup) as error:
        await driver.prepare(["result"], check_outputs=False).execute()
    rendered = "\n".join(record.getMessage() for record in caplog.records)
    rendered += f"\n{error.value}"
    assert any(isinstance(leaf, DataValidationError) for leaf in leaves(error.value))
    assert secret not in rendered
