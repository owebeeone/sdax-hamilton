"""C-family binding snapshots and public Hamilton conformance characterization."""

import asyncio
import inspect

import pytest

from sdax_hamilton._construction import resolve_nodes
from sdax_hamilton._hamilton_pipeline import (
    correct_copied_async_output_pipelines,
    snapshot_copied_macro_bindings,
    validate_copied_macro_bindings,
)
from sdax_hamilton._runtime import resolve
from sdax_hamilton.hamilton_compat import _copy_function


def _snapshot(fn):
    snapshot = _copy_function(fn)
    snapshot_copied_macro_bindings(snapshot)
    correct_copied_async_output_pipelines(snapshot)
    return snapshot


def _nodes(fn, config=None):
    return {entry.name: entry for entry in resolve_nodes(_snapshot(fn), dict(config or {}))}


def test_snapshot_matches_stock_macro_graph_and_values(module_factory, hamilton_oracle, graph_signature):
    source = """
from hamilton.function_modifiers import does, pipe_input, pipe_output, source, step, value
def replacement(number: int, offset: int = 1) -> int:
    return number + offset
@does(replacement)
def replaced(number: int, offset: int = 1) -> int:
    pass
def increase(value: int, amount: int) -> int:
    return value + amount
@pipe_input(step(increase, amount=value(2)), namespace="input")
def input_value(value: int) -> int:
    return value * 2
@pipe_output(step(increase, amount=source("increment")), namespace="output")
def output_value(value: int, increment: int) -> int:
    return value * 3
def result(replaced: int, input_value: int, output_value: int) -> int:
    return replaced + input_value + output_value
"""
    frontend_module = module_factory(source)
    oracle = hamilton_oracle(source)
    captured = {}
    for name in ("replaced", "input_value", "output_value", "result"):
        captured.update(_nodes(getattr(frontend_module, name)))

    oracle_signature = graph_signature(oracle.graph.nodes)
    assert graph_signature(captured) == {
        name: signature for name, signature in oracle_signature.items() if name in captured
    }
    assert oracle.execute(["result"], inputs={"number": 4, "value": 2, "increment": 5}) == {
        "result": 24
    }


@pytest.mark.parametrize(
    "selector",
    [
        lambda step: step.when(mode="enabled"),
        lambda step: step.when_not(mode="disabled"),
        lambda step: step.when_in(mode=["enabled"]),
        lambda step: step.when_not_in(mode=["disabled"]),
    ],
    ids=("when", "when_not", "when_in", "when_not_in"),
)
def test_known_step_config_selectors_are_snapshotted(module_factory, selector):
    modes = ["enabled"]
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, step
def increment(value: int) -> int:
    return value + 1
@pipe_input(selector(step(increment)))
def result(value: int) -> int:
    return value
""",
        modes=modes,
        selector=selector,
    )
    snapshot = _snapshot(module.result)
    from hamilton.function_modifiers import base

    assert {entry.name for entry in base.resolve_nodes(snapshot, {"mode": "enabled"})} == {
        "result",
        "result.with_increment",
    }


def test_step_selector_metadata_does_not_follow_mutated_list(module_factory):
    modes = ["enabled"]
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, step
def increment(value: int) -> int:
    return value + 1
@pipe_input(step(increment).when_in(mode=modes))
def result(value: int) -> int:
    return value
""",
        modes=modes,
    )
    snapshot = _snapshot(module.result)
    modes[:] = ["disabled"]
    from hamilton.function_modifiers import base

    assert {entry.name for entry in base.resolve_nodes(snapshot, {"mode": "enabled"})} == {
        "result",
        "result.with_increment",
    }
    assert {entry.name for entry in base.resolve_nodes(snapshot, {"mode": "disabled"})} == {
        "result"
    }


def test_unknown_step_selector_fails_before_expansion(module_factory):
    from hamilton.function_modifiers.configuration import ConfigResolver

    selector = ConfigResolver(lambda config: bool(config), ["mode"])
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, step
def increment(value: int) -> int:
    return value + 1
step_declaration = step(increment)
step_declaration.resolvers.append(selector)
@pipe_input(step_declaration)
def result(value: int) -> int:
    return value
""",
        selector=selector,
    )

    with pytest.raises(ValueError, match="unsupported Hamilton pipeline configuration selector"):
        _snapshot(module.result)


def test_deprecated_pipe_binding_is_copied(module_factory, caplog):
    module = module_factory("""
from hamilton.function_modifiers import pipe, step, value
def increment(value: int, amount: int) -> int:
    return value + amount
@pipe(step(increment, amount=value(2)))
def result(value: int) -> int:
    return value
""")
    from hamilton.function_modifiers import base

    assert any("pipe has been replaced with pipe_input" in record.message for record in caplog.records)
    assert {entry.name for entry in base.resolve_nodes(_snapshot(module.result), {})} == {
        "result",
        "result.with_increment",
    }


def test_binding_metadata_and_original_modifiers_are_isolated(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import does, pipe_output, source, step, value
def replacement(value: int) -> int:
    return value
@does(replacement, value="number")
def replaced(number: int) -> int:
    pass
def add(value: int, amount: int) -> int:
    return value + amount
@pipe_output(step(add, amount=source("increment")))
def result(value: int, increment: int) -> int:
    return value
""")
    replaced = _snapshot(module.replaced)
    result = _snapshot(module.result)
    original_mapping = module.replaced.generate[0].argument_mapping
    original_step = module.result.transform[0].transforms[0]

    original_mapping["value"] = "changed"
    original_step.kwargs["amount"].source = "changed"
    from hamilton.function_modifiers import base

    replaced_node = base.resolve_nodes(replaced, {})[0]
    result_nodes = {entry.name: entry for entry in base.resolve_nodes(result, {})}
    assert tuple(replaced_node.input_types) == ("number",)
    assert tuple(result_nodes["result.with_add"].input_types) == ("result.raw", "increment")
    assert result.transform[0] is not module.result.transform[0]
    assert result.transform[0].transforms[0] is not original_step


def test_plain_helper_code_and_defaults_are_snapshotted_without_decorator_traversal(
    module_factory,
):
    module = module_factory("""
from hamilton.function_modifiers import does, pipe_input, step
def replacement(value: int, offset: int = 1) -> int:
    return value + offset
@does(replacement)
def replaced(value: int, offset: int = 1) -> int:
    pass
def increment(value: int, offset: int = 1) -> int:
    return value + offset
@pipe_input(step(increment))
def piped(value: int) -> int:
    return value
def changed(value: int, offset: int = 9) -> int:
    return value + offset + 100
""")
    replaced = _snapshot(module.replaced)
    piped = _snapshot(module.piped)

    module.replacement.__code__ = module.changed.__code__
    module.replacement.__defaults__ = module.changed.__defaults__
    module.increment.__code__ = module.changed.__code__
    module.increment.__defaults__ = module.changed.__defaults__
    from hamilton.function_modifiers import base

    (replaced_node,) = base.resolve_nodes(replaced, {})
    piped_nodes = {entry.name: entry for entry in base.resolve_nodes(piped, {})}
    assert replaced_node.callable(value=2) == 3
    assert piped_nodes["piped.with_increment"].callable(value=2) == 3
    assert set(piped_nodes) == {"piped", "piped.with_increment"}


def test_mutate_is_captured_from_the_target_pipeline_and_remains_excluded(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import mutate, step, value
def target(value: int) -> int:
    return value * 2
@mutate(target, amount=value(3))
def add(value: int, amount: int) -> int:
    return value + amount
""")
    from hamilton.function_modifiers import base, step, value

    target = _snapshot(module.target)
    module.target.transform[0].transforms += (step(module.add, amount=value(9)),)

    assert [entry.name for entry in base.resolve_nodes(target, {})] == [
        "target.raw",
        "target.with_add",
        "target",
    ]
    assert base.resolve_nodes(module.add, {}) == []


@pytest.mark.asyncio
async def test_async_does_replacement_is_resolved_as_a_frontend_value(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import does
async def replacement(number: int) -> int:
    await asyncio.sleep(0)
    return number + 1
@does(replacement)
def result(number: int) -> int:
    pass
""",
        asyncio=asyncio,
    )
    (entry,) = _nodes(module.result).values()

    assert not inspect.iscoroutinefunction(entry.callable)
    assert await resolve(entry.callable(number=2)) == 3


@pytest.mark.parametrize(
    "source, name, message",
    [
        (
            """
from hamilton.function_modifiers import does
def replacement(number: str) -> int:
    return len(number)
@does(replacement)
def result(number: int) -> int:
    pass
""",
            "result",
            "replacement number: incompatible binding",
        ),
        (
            """
from hamilton.function_modifiers import does
def replacement(number: int) -> str:
    return str(number)
@does(replacement)
def result(number: int) -> int:
    pass
""",
            "result",
            "replacement return: incompatible binding",
        ),
    ],
)
def test_macro_preflight_rejects_hidden_binding_contract_errors(
    module_factory, source, name, message
):
    module = module_factory(source)

    with pytest.raises(TypeError, match=message):
        validate_copied_macro_bindings(_snapshot(getattr(module, name)))


def test_selected_pipeline_step_checks_captured_literals_once(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step, value
def add(value: int, offset: int) -> int:
    return value + offset
@pipe_output(step(add, offset=value("wrong")).when(mode="unsafe"))
def result(value: int) -> int:
    return value
""")
    snapshot = _snapshot(module.result)
    assert [entry.name for entry in resolve_nodes(snapshot, {"mode": "safe"})] == ["result"]
    with pytest.raises(TypeError, match="pipeline step.offset: bound literal has wrong type"):
        resolve_nodes(snapshot, {"mode": "unsafe"})


def test_mutually_exclusive_pipeline_steps_are_checked_only_on_the_selected_path(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step
def number(value: int) -> int:
    return value + 1
def text(value: int) -> str:
    return str(value)
@pipe_output(step(number).when(mode="number"), step(text).when(mode="text"))
def result(value: int) -> int:
    return value
""")
    from hamilton.function_modifiers import base

    snapshot = _snapshot(module.result)
    number_nodes = base.resolve_nodes(snapshot, {"mode": "number"})
    text_nodes = base.resolve_nodes(snapshot, {"mode": "text"})
    assert number_nodes[-1].type is int
    assert text_nodes[-1].type is str


def test_macro_preflight_validates_replacement_and_step_defaults(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import does, pipe_input, step
def replacement(number: int, offset: int = "wrong") -> int:
    return number
@does(replacement)
def replaced(number: int, offset: int = 1) -> int:
    pass
def add(value: int, offset: int = "wrong") -> int:
    return value
@pipe_input(step(add))
def piped(value: int) -> int:
    return value
""")

    with pytest.raises(TypeError, match="replacement.offset: invalid default"):
        validate_copied_macro_bindings(_snapshot(module.replaced))
    with pytest.raises(TypeError, match="pipeline step.offset: invalid default"):
        resolve_nodes(_snapshot(module.piped), {})
