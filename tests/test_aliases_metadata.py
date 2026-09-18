"""Phase-A Hamilton aliases, resolution controls, and inert metadata."""

import pytest

from sdax_hamilton import Driver
from sdax_hamilton._model import NodeSpec


@pytest.mark.asyncio
async def test_parameterization_aliases_match_stock_hamilton(
    module_factory, hamilton_oracle, graph_signature
):
    source = """
from hamilton.function_modifiers import (
    parameterize_sources,
    parameterize_values,
    parametrized,
    parametrized_input,
    parameterized_inputs,
)
def seed() -> int:
    return 4
@parameterize_values("value", {("modern_value", "modern value"): 2})
def modern_values(value: int) -> int:
    return value
@parameterize_sources(modern_source={"value": "seed"})
def modern_sources(value: int) -> int:
    return value
@parametrized("value", {("legacy_value", "legacy value"): 3})
def legacy_values(value: int) -> int:
    return value
@parametrized_input("value", {"seed": ("legacy_source", "legacy source")})
def legacy_sources(value: int) -> int:
    return value
@parameterized_inputs(legacy_inputs={"value": "seed"})
def legacy_inputs(value: int) -> int:
    return value
def result(
    modern_value: int,
    modern_source: int,
    legacy_value: int,
    legacy_source: int,
    legacy_inputs: int,
) -> int:
    return modern_value + modern_source + legacy_value + legacy_source + legacy_inputs
"""
    oracle = hamilton_oracle(source)
    frontend = Driver(module_factory(source))

    assert graph_signature(frontend._nodes) == graph_signature(oracle.graph.nodes)
    assert await frontend.prepare(["result"]).execute() == oracle.execute(["result"])


@pytest.mark.asyncio
async def test_custom_config_predicate_resolves_once_before_execution(module_factory):
    calls = []
    configuration = {"enabled": True}
    module = module_factory(
        """
from hamilton.function_modifiers import config
@config(predicate)
def result() -> int:
    calls.append("result")
    return 7
""",
        calls=calls,
        predicate=lambda values: calls.append(dict(values)) or values["enabled"],
    )

    driver = Driver(module, config=configuration)
    configuration["enabled"] = False
    assert calls == [{"enabled": True}]
    plan = driver.prepare(["result"])
    assert await plan.execute() == {"result": 7}
    assert await plan.execute() == {"result": 7}
    assert calls == [{"enabled": True}, "result", "result"]


@pytest.mark.asyncio
async def test_excluded_helper_need_not_be_graph_typed(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude
@hamilton_exclude
def helper(untyped):
    return untyped + 1
def result() -> int:
    return helper(6)
"""
    )

    assert await Driver(module).prepare(["result"]).execute() == {"result": 7}


def test_exclusion_cannot_hide_owned_declaration(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude
from sdax_hamilton import Acquisition, shutdown
@hamilton_exclude
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    pass
"""
    )

    with pytest.raises(ValueError, match="excluded declaration cannot own a shutdown"):
        Driver(module)


def test_excluded_helper_does_not_expand_unknown_modifier(module_factory):
    calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import base, hamilton_exclude
class Probe(base.NodeResolver):
    def validate(self, fn):
        pass
    def resolve(self, fn, config):
        calls.append("resolved")
        return fn
@hamilton_exclude
@Probe()
def helper(untyped):
    return untyped
def result() -> int:
    return 1
""",
        calls=calls,
    )

    Driver(module)
    assert calls == []


@pytest.mark.parametrize(
    "source",
    [
        """
from hamilton.function_modifiers import parameterize, value
class CustomParameterize(parameterize):
    pass
@CustomParameterize(result={"value": value(1)})
def result(value: int) -> int:
    return value
""",
        """
from hamilton.function_modifiers import tag
class CustomTag(tag):
    pass
@CustomTag(category="custom")
def result() -> int:
    return 1
""",
    ],
)
def test_unreviewed_decorator_subclasses_remain_rejected(module_factory, source):
    with pytest.raises(ValueError, match="unsupported Hamilton decorator"):
        Driver(module_factory(source))


def test_metadata_matches_stock_and_is_snapshotted(module_factory, hamilton_oracle, graph_signature):
    source = """
from hamilton.function_modifiers import cache, parameterize, tag, tag_outputs, value
from hamilton.function_modifiers.metadata import ray_remote_options
@ray_remote_options(num_cpus=2)
@cache(behavior="recompute", format="json")
@tag_outputs(left={"branch": "left"}, right={"branch": "right"})
@parameterize(left={"value": value(1)}, right={"value": value(2)})
@tag(category="phase-a")
def result(value: int) -> int:
    return value
"""
    tag_keys = (
        "category",
        "branch",
        "cache.behavior",
        "cache.format",
        "ray_remote.num_cpus",
    )
    oracle = hamilton_oracle(source)
    frontend = Driver(module_factory(source))

    assert graph_signature(frontend._nodes, tag_keys=tag_keys) == graph_signature(
        oracle.graph.nodes, tag_keys=tag_keys
    )
    with pytest.raises(TypeError):
        frontend._nodes["left"].tags["category"] = "changed"


def test_schema_output_metadata_matches_stock_hamilton(module_factory, hamilton_oracle, graph_signature):
    source = """
import pandas as pd
from hamilton.function_modifiers import schema
@schema.output(("score", "int"))
def result() -> pd.DataFrame:
    return pd.DataFrame({"score": [1]})
"""
    tag_keys = ("hamilton.internal.schema_output",)
    oracle = hamilton_oracle(source)
    frontend = Driver(module_factory(source))

    assert graph_signature(frontend._nodes, tag_keys=tag_keys) == graph_signature(
        oracle.graph.nodes, tag_keys=tag_keys
    )


def test_tag_snapshot_copies_its_container_but_keeps_value_identity():
    marker = object()
    tags = {"marker": marker}
    spec = NodeSpec("result", lambda: marker, object, {}, tags=tags)
    tags["later"] = marker

    assert spec.tags == {"marker": marker}
    assert spec.tags["marker"] is marker


def test_tag_snapshot_copies_list_metadata_containers(module_factory):
    labels = ["initial"]
    module = module_factory(
        """
from hamilton.function_modifiers import tag
@tag(labels=labels)
def result() -> int:
    return 1
""",
        labels=labels,
    )
    driver = Driver(module)
    labels.append("changed")

    assert driver._nodes["result"].tags["labels"] == ["initial"]
    assert driver._nodes["result"].tags["labels"] is not labels


@pytest.mark.asyncio
async def test_cache_and_ray_tags_do_not_enable_backend_execution(module_factory):
    calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import cache
from hamilton.function_modifiers.metadata import ray_remote_options
@ray_remote_options(num_cpus=2)
@cache(behavior="default", format="pickle")
def result() -> int:
    calls.append("local")
    return len(calls)
""",
        calls=calls,
    )

    plan = Driver(module).prepare(["result"])
    assert await plan.execute() == {"result": 1}
    assert await plan.execute() == {"result": 2}
    assert calls == ["local", "local"]
