"""Original-consumer requirements stay checked through every binding path."""

from typing import Any

import pytest

from sdax_hamilton._model import InputSpec, NodeSpec
from sdax_hamilton.plan import PreparedPlan


def node(name, output_type, fn, inputs=()):
    return NodeSpec(name, fn, output_type, dict(inputs))


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
