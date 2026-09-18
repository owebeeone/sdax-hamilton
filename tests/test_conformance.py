"""Shared stock-Hamilton oracle exercised against the qualified baseline."""

import pytest

from sdax_hamilton import Driver


@pytest.mark.asyncio
async def test_oracle_graph_and_values_match_baseline(module_factory, hamilton_oracle, graph_signature):
    source = """
from hamilton.function_modifiers import config, inject, parameterize, source, value
@config.when(mode="a")
def seed__a() -> int:
    return 3
@config.when(mode="b")
def seed__b() -> int:
    return 7
@parameterize(left={"number": source("seed")}, right={"number": value(5)})
def double(number: int) -> int:
    return number * 2
@inject(offset=value(2))
def result(left: int, right: int, offset: int, extra: int = 4) -> int:
    return left + right + offset + extra
"""
    for mode in ("a", "b"):
        config = {"mode": mode}
        oracle = hamilton_oracle(source, config=config)
        frontend = Driver(module_factory(source), config=config)
        assert graph_signature(frontend._nodes) == graph_signature(oracle.graph.nodes)
        assert await frontend.prepare(["result"]).execute() == oracle.execute(["result"])


def test_oracle_preserves_requested_metadata_without_collecting_values(hamilton_oracle, graph_signature):
    sentinel = object()
    oracle = hamilton_oracle(
        """
from hamilton.function_modifiers import tag
@tag(category="conformance")
def result() -> object:
    return sentinel
""",
        sentinel=sentinel,
    )
    signature = graph_signature(oracle.graph.nodes, tag_keys=("category",))
    assert signature == {"result": (object, {}, frozenset(), {"category": "conformance"})}


def test_oracle_construction_does_not_run_user_nodes(hamilton_oracle):
    calls = []
    oracle = hamilton_oracle(
        """
def result() -> int:
    calls.append("result")
    return 1
""",
        calls=calls,
    )
    assert calls == []
    assert oracle.execute(["result"]) == {"result": 1}
    assert calls == ["result"]


def test_oracle_does_not_hide_original_user_exception(hamilton_oracle):
    error = ValueError("synthetic failure")
    oracle = hamilton_oracle(
        """
def result() -> int:
    raise error
""",
        error=error,
    )
    with pytest.raises(ValueError) as caught:
        oracle.execute(["result"])
    assert caught.value is error
