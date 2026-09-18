import inspect
from functools import partial
from typing import get_type_hints

import pytest
from hamilton.function_modifiers import (
    configuration,
    extract_columns,
    extract_fields,
    group,
    inject,
    parameterize_extract_columns,
    source,
    unpack_fields,
    value,
)

from sdax_hamilton import Driver, hamilton_compat
from sdax_hamilton import driver as driver_module
from sdax_hamilton._hamilton_bindings import capture_bindings
from sdax_hamilton._model import MISSING


def _capture(fn, modifier):
    return capture_bindings(fn, modifier, get_type_hints(fn, include_extras=True), inspect.signature(fn).parameters)


@pytest.fixture(autouse=True)
def _admit_binding_families(monkeypatch):
    """Exercise exact B surfaces without extending the public supported set."""
    monkeypatch.setattr(
        driver_module,
        "compile_modules",
        partial(
            hamilton_compat.compile_modules,
            _supported=(
                *hamilton_compat._SUPPORTED,
                extract_fields,
                extract_columns,
                unpack_fields,
                parameterize_extract_columns,
            ),
        ),
    )


def test_binding_capture_preserves_merged_source_requirements_and_original_defaults():
    def result(left: int, shared: int | str = 3) -> int:
        return left

    captured = _capture(result, inject(left=source("shared")))
    binding = captured["result"]["shared"]

    assert binding.requirements == (int, int | str)
    assert binding.default == 3


def test_binding_capture_completes_an_optional_rebound_source_default():
    def result(value: int = 7) -> int:
        return value

    captured = _capture(result, inject(value=source("seed")))
    binding = captured["result"]["seed"]

    assert binding.requirements == (int,)
    assert binding.default == 7


def test_binding_capture_preserves_an_identical_merged_source_default():
    def result(first: int = 3, second: int = 3) -> int:
        return first + second

    captured = _capture(
        result,
        inject(first=source("seed"), second=source("seed")),
    )

    assert captured["result"]["seed"].default == 3


def test_binding_capture_requires_a_merged_source_when_any_consumer_is_required():
    def result(first: int, second: int = 3) -> int:
        return first + second

    captured = _capture(
        result,
        inject(first=source("seed"), second=source("seed")),
    )

    assert captured["result"]["seed"].default is MISSING


def test_binding_capture_rejects_conflicting_merged_source_defaults():
    def result(first: int = 3, second: int = 4) -> int:
        return first + second

    with pytest.raises(ValueError, match="conflicting merged source defaults"):
        _capture(
            result,
            inject(first=source("other"), second=source("other")),
        )


@pytest.mark.asyncio
async def test_stock_optional_source_rebinding_requires_a_source_value(hamilton_oracle):
    source_text = """
from hamilton.function_modifiers import inject, source

@inject(value=source("seed"))
def result(value: int = 7) -> int:
    return value
"""
    oracle = hamilton_oracle(source_text)

    with pytest.raises(KeyError, match="seed"):
        oracle.execute(["result"])
    assert oracle.execute(["result"], inputs={"seed": 4}) == {"result": 4}


def test_binding_capture_admits_direct_group_values_and_source_defaults():
    def result(seed: int = 3, values: list[int] = []) -> int:
        return seed + sum(values)

    captured = _capture(result, inject(values=group(source("seed"), value(2))))
    binding = captured["result"]["seed"]

    assert binding.requirements == (int, int)
    assert binding.default == 3


def test_binding_capture_tracks_parameterize_extract_columns_outputs():
    from hamilton.function_modifiers import ParameterizedExtract, parameterize_extract_columns

    def columns(number: int, seed: int = 3) -> object:
        return number + seed

    modifier = parameterize_extract_columns(
        ParameterizedExtract(("number",), {"number": source("seed")})
    )
    captured = _capture(columns, modifier)

    assert set(captured) == {"columns__0"}
    assert captured["columns__0"]["seed"].requirements == (int, int)
    assert captured["columns__0"]["seed"].default == 3


def _invalid_config_group():
    values = group(source("seed"))
    values.sources.append(configuration("unsafe"))
    return inject(values=values)


@pytest.mark.parametrize(
    "modifier, message",
    (
        (inject(values=group(value("wrong"))), "bound literal"),
        (_invalid_config_group(), "direct source/value"),
    ),
)
def test_binding_capture_rejects_unsafe_group_neighbors(modifier, message):
    def result(values: list[int]) -> int:
        return sum(values)

    with pytest.raises((TypeError, ValueError), match=message):
        _capture(result, modifier)


@pytest.mark.asyncio
async def test_direct_source_value_and_group_bindings_match_stock(module_factory, hamilton_oracle, graph_signature):
    source = """
from hamilton.function_modifiers import group, inject, source, value

@inject(
    numbers=group(source("left"), value(3), source("right")),
    named=group(first=source("left"), second=value(5)),
)
def result(numbers: list[int], named: dict[str, int]) -> int:
    return sum(numbers) + sum(named.values())
"""
    module = module_factory(source)
    frontend = Driver(module)
    oracle = hamilton_oracle(source)

    assert graph_signature(frontend._nodes) == graph_signature(oracle.graph.nodes)
    assert await frontend.prepare(["result"]).execute(inputs={"left": 2, "right": 4}) == {
        "result": 16
    }


@pytest.mark.parametrize(
    "source",
    (
        """
from hamilton.function_modifiers import configuration, group, inject, source
binding = group(source("seed"))
binding.sources.append(configuration("unsafe"))
@inject(values=binding)
def result(values: list[int]) -> int:
    return sum(values)
""",
        """
from hamilton.function_modifiers import group, inject, source
binding = group(source("seed"))
binding.sources.append(group(source("nested")))
@inject(values=binding)
def result(values: list[int]) -> int:
    return sum(values)
""",
    ),
)
def test_group_rejects_mutated_config_and_nested_forms_before_execution(
    module_factory, source
):
    calls: list[str] = []
    module = module_factory(source, calls=calls)

    with pytest.raises((TypeError, ValueError), match="group"):
        Driver(module)
    assert calls == []


def test_group_literal_is_checked_against_its_element_type_before_execution(module_factory):
    calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import group, inject, value

@inject(values=group(value("wrong")))
def result(values: list[int]) -> int:
    calls.append("called")
    return sum(values)
""",
        calls=calls,
    )

    with pytest.raises(TypeError, match="bound literal"):
        Driver(module)
    assert calls == []


@pytest.mark.asyncio
async def test_merged_source_preserves_all_original_requirements(module_factory):
    calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import inject, source

@inject(left=source("shared"))
def result(left: int, shared: int | str) -> int:
    calls.append("result")
    return left
""",
        calls=calls,
    )
    driver = Driver(module)
    binding = driver._nodes["result"].inputs["shared"]

    assert binding.requirements == (int, int | str)
    assert await driver.prepare(["result"]).execute(inputs={"shared": 4}) == {"result": 4}
    calls.clear()
    with pytest.raises(TypeError, match="Invalid input"):
        await driver.prepare(["result"]).execute(inputs={"shared": "unsafe"})
    assert calls == []


@pytest.mark.asyncio
async def test_source_to_original_default_is_completed_at_the_call_boundary(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import inject, source

@inject(left=source("shared"))
def result(left: int, shared: int = 3) -> int:
    return left + shared
"""
    )
    driver = Driver(module)

    assert await driver.prepare(["result"]).execute() == {"result": 6}
    assert await driver.prepare(["result"], optional_inputs=["shared"]).execute(
        inputs={"shared": 4}
    ) == {"result": 8}


@pytest.mark.asyncio
async def test_config_resolved_inject_remaps_the_placeholder_capture(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import config, inject, source

@config.when(mode="one")
@inject(left=source("shared"))
def result__one(left: int, shared: int | str = 3) -> int:
    return left
"""
    )

    driver = Driver(module, config={"mode": "one"})

    assert driver._nodes["result"].inputs["shared"].requirements == (int, int | str)
    assert await driver.prepare(["result"]).execute() == {"result": 3}
    assert await driver.prepare(["result"], optional_inputs=["shared"]).execute(
        inputs={"shared": 4}
    ) == {"result": 4}


@pytest.mark.asyncio
async def test_config_resolved_parameterize_extract_columns_remaps_synthesized_outputs(
    module_factory,
):
    module = module_factory(
        """
import pandas as pd

from hamilton.function_modifiers import (
    ParameterizedExtract,
    config,
    parameterize_extract_columns,
    source,
)

@config.when(mode="one")
@parameterize_extract_columns(
    ParameterizedExtract(("left",), {"number": source("seed")}),
)
def columns__one(number: int) -> pd.DataFrame:
    return pd.DataFrame({"left": [number]})
"""
    )

    driver = Driver(module, config={"mode": "one"})

    assert driver._nodes["columns__0"].inputs["seed"].requirements == (int,)
    assert (await driver.prepare(["left"]).execute(inputs={"seed": 4}))["left"].tolist() == [
        4
    ]


@pytest.mark.asyncio
async def test_group_binding_snapshot_keeps_direct_source_metadata(module_factory):
    from hamilton.function_modifiers import group, source, value

    first = source("first")
    binding = group(first, value(3))
    module = module_factory(
        """
from hamilton.function_modifiers import inject

@inject(values=binding)
def result(values: list[int]) -> int:
    return sum(values)
""",
        binding=binding,
    )
    driver = Driver(module)
    first.source = "changed_after_construction"

    assert await driver.prepare(["result"]).execute(inputs={"first": 2}) == {"result": 5}


@pytest.mark.asyncio
async def test_extract_fields_unpack_fields_and_extract_columns_match_stock(module_factory, hamilton_oracle, graph_signature):
    source = """
import pandas as pd

from typing import TypedDict
from hamilton.function_modifiers import extract_columns, extract_fields, unpack_fields

class Payload(TypedDict):
    number: int

@extract_fields()
def fields(seed: int) -> Payload:
    return {"number": seed}

@unpack_fields("tuple_number", "tuple_name")
def unpacked(seed: int) -> tuple[int, str]:
    return seed + 1, "ok"

@extract_columns("column_number", "column_double")
def frame(seed: int) -> pd.DataFrame:
    return pd.DataFrame({"column_number": [seed], "column_double": [seed * 2]})

def result(number: int, tuple_number: int, tuple_name: str, column_number: pd.Series, column_double: pd.Series) -> int:
    return number + tuple_number + len(tuple_name) + int(column_number.iloc[0]) + int(column_double.iloc[0])
"""
    module = module_factory(source)
    frontend = Driver(module)
    oracle = hamilton_oracle(source)

    frontend_signature = graph_signature(frontend._nodes)
    oracle_signature = graph_signature(oracle.graph.nodes)
    for name in ("fields", "number"):
        frontend_signature.pop(name)
        oracle_signature.pop(name)
    assert frontend_signature == oracle_signature
    assert frontend._nodes["fields"].output_type.__name__ == oracle.graph.nodes[
        "fields"
    ].type.__name__
    assert frontend._nodes["number"].inputs["fields"].typ.__name__ == oracle.graph.nodes[
        "number"
    ].input_types["fields"][0].__name__
    assert await frontend.prepare(["result"]).execute(inputs={"seed": 2}) == {"result": 13}


@pytest.mark.asyncio
async def test_parameterize_extract_columns_matches_stock_names_edges_tags_and_values(
    module_factory, hamilton_oracle, graph_signature
):
    source = """
import pandas as pd

from hamilton.function_modifiers import (
    ParameterizedExtract,
    parameterize_extract_columns,
    source,
    tag,
    value,
)

@tag(boundary="bindings")
@parameterize_extract_columns(
    ParameterizedExtract(("left", "left_double"), {"number": source("seed")}),
    ParameterizedExtract(("right", "right_double"), {"number": value(3)}),
)
def columns(number: int) -> pd.DataFrame:
    return pd.DataFrame({"one": [number], "two": [number * 2]})

def result(left: pd.Series, left_double: pd.Series, right: pd.Series, right_double: pd.Series) -> int:
    return int(left.iloc[0] + left_double.iloc[0] + right.iloc[0] + right_double.iloc[0])
"""
    module = module_factory(source)
    frontend = Driver(module)
    oracle = hamilton_oracle(source)

    assert graph_signature(frontend._nodes, tag_keys=("boundary",)) == graph_signature(
        oracle.graph.nodes, tag_keys=("boundary",)
    )
    assert await frontend.prepare(["result"]).execute(inputs={"seed": 2}) == {"result": 15}


@pytest.mark.asyncio
async def test_owned_extract_field_projection_borrows_and_releases_its_actual_owner(module_factory):
    from sdax_hamilton._model import GeneratedRole

    events: list[object] = []
    module = module_factory(
        """
from typing import TypedDict

from hamilton.function_modifiers import extract_fields
from sdax_hamilton import Acquisition, shutdown

class Payload(TypedDict):
    number: int

@extract_fields()
def owner() -> Payload:
    events.append("acquire")
    return {"number": 4}

@shutdown(of=owner)
def close(state: Acquisition[Payload]) -> None:
    events.append(("release", state.raw_value["number"]))
""",
        events=events,
    )
    driver = Driver(module)

    assert driver._nodes["owner"].role is GeneratedRole.VALUE
    assert driver._nodes["number"].role is GeneratedRole.PROJECTION
    assert driver._nodes["number"].borrow_from == frozenset({"owner"})
    async with driver.prepare(["number"]).open() as result:
        assert result == {"number": 4}
    assert events == ["acquire", ("release", 4)]


@pytest.mark.asyncio
async def test_invalid_owned_raw_extract_releases_once_without_running_projection(module_factory):
    events: list[object] = []
    module = module_factory(
        """
from typing import TypedDict

from hamilton.function_modifiers import extract_fields
from sdax_hamilton import Acquisition, shutdown

class Payload(TypedDict):
    number: int

@extract_fields()
def owner() -> Payload:
    events.append("acquire")
    return {"number": "wrong"}

@shutdown(of=owner)
def close(state: Acquisition[Payload]) -> None:
    events.append(("release", state.raw_value["number"]))
""",
        events=events,
    )
    plan = Driver(module).prepare(["number"])

    with pytest.raises(BaseExceptionGroup):
        async with plan.open():
            pass
    assert events == ["acquire", ("release", "wrong")]
