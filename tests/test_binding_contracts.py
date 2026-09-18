"""Original-consumer requirements stay checked through every binding path."""

import inspect
from typing import Any, get_type_hints

import pytest
from hamilton.function_modifiers import (
    configuration,
    group,
    inject,
    parameterize,
    source,
    value,
)

from sdax_hamilton._hamilton_bindings import capture_bindings, snapshot_binding_containers
from sdax_hamilton._model import MISSING, InputSpec, NodeSpec
from sdax_hamilton.plan import PreparedPlan


def node(name, output_type, fn, inputs=()):
    return NodeSpec(name, fn, output_type, dict(inputs))


def _capture(fn, modifier):
    return capture_bindings(
        fn,
        modifier,
        get_type_hints(fn, include_extras=True),
        inspect.signature(fn).parameters,
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


def test_binding_snapshot_copies_group_dependencies_but_preserves_literal_payload_identity():
    def result(values: list[object]) -> int:
        return len(values)

    source_dependency = source("seed")
    payload = {"identity": "kept"}
    modifier = inject(values=group(source_dependency, value(payload)))

    snapshot_binding_containers(modifier)
    source_dependency.source = "changed_after_snapshot"
    grouped = modifier.parameterization[parameterize.PLACEHOLDER_PARAM_NAME]["values"]

    assert grouped.sources[1].value is payload
    assert set(_capture(result, modifier)["result"]) == {"seed"}


def test_parameterize_extract_snapshot_copies_its_direct_source_mapping():
    from hamilton.function_modifiers import ParameterizedExtract, parameterize_extract_columns

    def columns(number: int) -> object:
        return number

    source_dependency = source("seed")
    modifier = parameterize_extract_columns(
        ParameterizedExtract(("number",), {"number": source_dependency})
    )

    snapshot_binding_containers(modifier)
    source_dependency.source = "changed_after_snapshot"

    assert set(_capture(columns, modifier)["columns__0"]) == {"seed"}


def leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for nested in error.exceptions for leaf in leaves(nested)]
    return [error]


def test_input_requirement_defaults_to_declared_type():
    binding = InputSpec(int)

    assert binding.requirements == ()
    assert binding.effective_requirements == (int,)


@pytest.mark.asyncio
async def test_original_requirement_accepts_compatible_edge():
    nodes = {
        "source": node("source", int, lambda: 7),
        "result": node(
            "result",
            int,
            lambda source: source,
            (("source", InputSpec(object, requirements=(int,))),),
        ),
    }

    assert await PreparedPlan(nodes, ["result"]).execute() == {"result": 7}


def test_original_requirement_rejects_unsafe_edge_before_execution():
    nodes = {
        "source": node("source", str, lambda: "wrong"),
        "result": node(
            "result",
            int,
            lambda source: source,
            (("source", InputSpec(object, requirements=(int,))),),
        ),
    }

    with pytest.raises(TypeError, match="Incompatible edge"):
        PreparedPlan(nodes, ["result"])


def test_original_requirement_rejects_invalid_default_before_execution():
    nodes = {
        "result": node(
            "result",
            int,
            lambda value: 1,
            (("value", InputSpec(object, default="wrong", requirements=(int,))),),
        )
    }

    with pytest.raises(TypeError, match="Invalid default"):
        PreparedPlan(nodes, ["result"])


@pytest.mark.parametrize(
    "nodes, configuration, message",
    [
        (
            {
                "result": node(
                    "result",
                    int,
                    lambda value: 1,
                    (("value", InputSpec(object, requirements=(int,))),),
                )
            },
            {"value": "wrong"},
            "Invalid config input",
        ),
        (
            {
                "source": node("source", Any, lambda: 1),
                "result": node(
                    "result",
                    int,
                    lambda source: 1,
                    (("source", InputSpec(object, requirements=(int,))),),
                ),
            },
            {"source": "wrong"},
            "Invalid config replacement",
        ),
    ],
)
def test_original_requirement_rejects_invalid_configuration(nodes, configuration, message):
    with pytest.raises(TypeError, match=message):
        PreparedPlan(nodes, ["result"], config=configuration)


@pytest.mark.asyncio
async def test_external_input_requirement_fails_before_any_callback():
    calls = []
    nodes = {
        "result": node(
            "result",
            int,
            lambda value: calls.append("result") or 1,
            (("value", InputSpec(object, requirements=(int,))),),
        )
    }
    plan = PreparedPlan(nodes, ["result"])

    with pytest.raises(TypeError, match="Invalid input"):
        await plan.execute(inputs={"value": "wrong"})
    assert calls == []


@pytest.mark.asyncio
async def test_conjunctive_external_requirements_reject_before_independent_effects():
    calls = []
    nodes = {
        "permissive": node(
            "permissive",
            int,
            lambda shared: calls.append("permissive") or 1,
            (("shared", InputSpec(int | str)),),
        ),
        "restricted": node(
            "restricted",
            int,
            lambda shared: calls.append("restricted") or 1,
            (("shared", InputSpec(int | str, requirements=(int | str, int))),),
        ),
        "independent": node("independent", int, lambda: calls.append("independent") or 1),
    }
    plan = PreparedPlan(nodes, ["permissive", "restricted", "independent"])

    assert await plan.execute(inputs={"shared": 7}) == {
        "permissive": 1,
        "restricted": 1,
        "independent": 1,
    }
    calls.clear()
    with pytest.raises(TypeError, match="Invalid input"):
        await plan.execute(inputs={"shared": "accepted only by the union"})
    assert calls == []


@pytest.mark.asyncio
async def test_override_requirement_fails_before_any_callback():
    calls = []
    nodes = {
        "source": node("source", Any, lambda: calls.append("source") or 1),
        "result": node(
            "result",
            int,
            lambda source: calls.append("result") or source,
            (("source", InputSpec(object, requirements=(int,))),),
        ),
    }
    plan = PreparedPlan(nodes, ["result"], override_nodes=["source"])

    with pytest.raises(TypeError, match="Invalid override"):
        await plan.execute(overrides={"source": "wrong"})
    assert calls == []


@pytest.mark.asyncio
async def test_conjunctive_override_rejects_before_independent_effects():
    calls = []
    nodes = {
        "source": node("source", Any, lambda: calls.append("source") or 1),
        "permissive": node(
            "permissive",
            int,
            lambda source: calls.append("permissive") or 1,
            (("source", InputSpec(int | str)),),
        ),
        "restricted": node(
            "restricted",
            int,
            lambda source: calls.append("restricted") or 1,
            (("source", InputSpec(int | str, requirements=(int | str, int))),),
        ),
        "independent": node("independent", int, lambda: calls.append("independent") or 1),
    }
    plan = PreparedPlan(
        nodes,
        ["permissive", "restricted", "independent"],
        override_nodes=["source"],
    )

    with pytest.raises(TypeError, match="Invalid override"):
        await plan.execute(overrides={"source": "accepted only by the union"})
    assert calls == []


@pytest.mark.asyncio
async def test_generated_value_meets_requirement_before_consumer_callback():
    calls = []
    nodes = {
        "source": node("source", Any, lambda: calls.append("source") or "wrong"),
        "result": node(
            "result",
            int,
            lambda source: calls.append("result") or source,
            (("source", InputSpec(Any, requirements=(int,))),),
        ),
    }
    plan = PreparedPlan(nodes, ["result"], check_outputs=False)

    with pytest.raises(BaseExceptionGroup) as errors:
        await plan.execute()
    assert any(isinstance(error, TypeError) for error in leaves(errors.value))
    assert calls == ["source"]


@pytest.mark.asyncio
async def test_invalid_generated_value_releases_upstream_once():
    calls = []
    nodes = {
        "source": NodeSpec(
            "source",
            lambda: calls.append("source") or "wrong",
            Any,
            {},
            release=lambda state: calls.append(f"release:{state.value}"),
        ),
        "result": node(
            "result",
            int,
            lambda source: calls.append("result") or source,
            (("source", InputSpec(Any, requirements=(int,))),),
        ),
    }
    plan = PreparedPlan(nodes, ["result"], check_outputs=False)

    with pytest.raises(BaseExceptionGroup) as errors:
        await plan.execute()
    assert any(isinstance(error, TypeError) for error in leaves(errors.value))
    assert calls == ["source", "release:wrong"]
