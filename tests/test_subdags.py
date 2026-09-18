"""Public Driver qualification for exact Hamilton subdag declaration forms."""

import logging

import pytest

from sdax_hamilton import Driver


@pytest.mark.asyncio
async def test_subdag_module_preserves_inputs_config_external_inputs_and_namespace(module_factory):
    nested = module_factory(
        """
def base(raw: int) -> int:
    return raw

def adjusted(base: int, offset: int) -> int:
    return base + offset
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import source, subdag

@subdag(
    nested,
    inputs={"raw": source("seed")},
    config={"offset": 2},
    namespace="mounted",
    external_inputs=["external"],
)
def result(adjusted: int, external: int) -> int:
    return adjusted + external
""",
        nested=nested,
    )

    driver = Driver(root)
    plan = driver.prepare(["result"])

    assert plan.required_inputs == {"external": (int,), "seed": (int,)}
    assert await plan.execute(inputs={"seed": 3, "external": 4}) == {"result": 9}
    assert {"mounted.base", "mounted.adjusted", "mounted.raw", "mounted.offset"} <= set(
        driver._nodes
    )


@pytest.mark.asyncio
async def test_parameterized_subdag_accepts_direct_function_sources_and_mount_options(module_factory):
    nested = module_factory(
        """
def base(raw: int) -> int:
    return raw

def adjusted(base: int, offset: int) -> int:
    return base + offset
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import parameterized_subdag, source

@parameterized_subdag(
    base,
    adjusted,
    inputs={"raw": source("seed")},
    first={"config": {"offset": 2}},
    second={"inputs": {"raw": source("other")}, "config": {"offset": 3}},
)
def mounted(adjusted: int) -> int:
    return adjusted
""",
        base=nested.base,
        adjusted=nested.adjusted,
    )

    driver = Driver(root)

    assert await driver.prepare(["first", "second"]).execute(
        inputs={"seed": 4, "other": 5}
    ) == {"first": 6, "second": 8}
    assert {"first.base", "first.adjusted", "second.base", "second.adjusted"} <= set(
        driver._nodes
    )


@pytest.mark.asyncio
async def test_parameterized_subdag_preserves_original_contracts_through_namespace(module_factory):
    nested = module_factory(
        """
from hamilton.function_modifiers import inject, source

@inject(left=source("shared"))
def component(left: int, shared: int | str = 3) -> int:
    return left
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import parameterized_subdag

@parameterized_subdag(component, low={})
def result(component: int) -> int:
    return component
""",
        component=nested.component,
    )

    driver = Driver(root)
    binding = driver._nodes["low.component"].inputs["shared"]

    assert binding.typ == int | str
    assert binding.default == 3
    assert binding.requirements == (int, int | str)
    assert await driver.prepare(["low"]).execute() == {"low": 3}
    optional = driver.prepare(["low"], optional_inputs=["shared"])
    with pytest.raises(TypeError, match="Invalid input: shared"):
        await optional.execute(inputs={"shared": "unsafe"})


@pytest.mark.asyncio
async def test_subdag_mounts_keep_resources_and_shutdowns_local(module_factory):
    acquired: list[int] = []
    released: list[int] = []
    nested = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def resource() -> int:
    identifier = len(acquired) + 1
    acquired.append(identifier)
    return identifier

def value(resource: int) -> int:
    return resource * 10

@shutdown(of=resource)
def close(state: Acquisition[int]) -> None:
    if state.has_value:
        released.append(state.value)
""",
        acquired=acquired,
        released=released,
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested, namespace="first")
def first(value: int) -> int:
    return value

@subdag(nested, namespace="second")
def second(value: int) -> int:
    return value
""",
        nested=nested,
    )

    result = await Driver(root).prepare(["first", "second"]).execute()

    assert result == {"first": 10, "second": 20}
    assert acquired == [1, 2]
    assert sorted(released) == [1, 2]


def test_nested_construction_error_is_original_once_and_unlogged(module_factory, caplog):
    sentinel = ValueError("nested subdag config sentinel")
    calls: list[dict[str, object]] = []

    def predicate(values):
        calls.append(dict(values))
        raise sentinel

    nested = module_factory(
        """
from hamilton.function_modifiers import config

@config(predicate)
def value() -> int:
    return 1
""",
        predicate=predicate,
        calls=calls,
        sentinel=sentinel,
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested)
def result(value: int) -> int:
    return value
""",
        nested=nested,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as caught:
            Driver(root, config={"enabled": True})

    assert caught.value is sentinel
    assert calls == [{"enabled": True}]
    assert not [
        record for record in caplog.records if record.name == "hamilton.function_modifiers.base"
    ]


def test_subdag_cycle_rejects_before_hamilton_resolution(module_factory):
    first = module_factory("def first() -> int:\n    return 1")
    second = module_factory("def second() -> int:\n    return 2")
    from hamilton.function_modifiers import subdag

    first.first = subdag(second.second)(first.first)
    second.second = subdag(first.first)(second.second)

    with pytest.raises(ValueError, match="Recursive subdag declaration cycle"):
        Driver(first)


@pytest.mark.parametrize("replacement", ["config", "override"])
def test_owned_nested_acquisition_cannot_be_replaced_before_effects(module_factory, replacement):
    effects: list[str] = []
    nested = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown

def resource() -> int:
    effects.append("acquire")
    return 7

def value(resource: int) -> int:
    return resource

@shutdown(of=resource)
def close(state: Acquisition[int]) -> None:
    effects.append("release")
""",
        effects=effects,
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested, namespace="mounted")
def result(value: int) -> int:
    return value
""",
        nested=nested,
    )

    driver = Driver(root, config={"mounted.resource": 9} if replacement == "config" else None)
    if replacement == "config":
        with pytest.raises(ValueError, match="Cannot replace owned acquisition: mounted.resource"):
            driver.prepare(["result"])
    else:
        with pytest.raises(ValueError, match="Cannot replace owned acquisition: mounted.resource"):
            driver.prepare(["result"], override_nodes=["mounted.resource"])

    assert effects == []


@pytest.mark.asyncio
async def test_subdag_preserves_pipeline_input_contracts_through_namespace(module_factory):
    nested = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step

def increment(value: int = 2) -> int:
    return value + 1

@pipe_output(step(increment))
def inner() -> int:
    return 3
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(inner)
def result(inner: int) -> int:
    return inner
""",
        inner=nested.inner,
    )

    driver = Driver(root)
    generated = [
        spec for name, spec in driver._nodes.items() if name.endswith(".with_increment")
    ]

    assert len(generated) == 1
    bindings = list(generated[0].inputs.values())
    assert len(bindings) == 1
    assert bindings[0].default == 2
    assert bindings[0].requirements == (int,)
    assert await driver.prepare(["result"]).execute() == {"result": 4}
