"""End-to-end qualification targets for proposed phase-C macro admission.

These tests deliberately exercise Driver and PreparedPlan, rather than the
private expansion helpers.  They remain separate while P2 wires provenance
capture into the production compiler.
"""

import asyncio
from functools import partial

import pytest
from hamilton.function_modifiers import does, pipe, pipe_input, pipe_output, value

from sdax_hamilton import Driver, hamilton_compat
from sdax_hamilton import driver as driver_module


@pytest.fixture(autouse=True)
def _provisional_c_admission(monkeypatch):
    """Qualify the implementation while the public QB admission gate stays closed.

    Remove this finite test-only harness when QB enables these exact classes.
    """
    monkeypatch.setattr(
        driver_module,
        "compile_modules",
        partial(
            hamilton_compat.compile_modules,
            _supported=(*hamilton_compat._SUPPORTED, does, pipe, pipe_input, pipe_output),
        ),
    )


@pytest.mark.asyncio
async def test_driver_executes_sync_input_and_output_pipelines(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_input, pipe_output, source, step, value

def add(value: int, amount: int) -> int:
    return value + amount

@pipe_input(step(add, amount=value(2)), namespace="input")
def input_value(value: int) -> int:
    return value * 3

@pipe_output(step(add, amount=source("offset")), namespace="output")
def output_value(value: int, offset: int) -> int:
    return value * 3

def result(input_value: int, output_value: int) -> int:
    return input_value + output_value
""")

    plan = Driver(module).prepare(["result"])
    assert await plan.execute(inputs={"value": 2, "offset": 4}) == {"result": 22}


@pytest.mark.asyncio
async def test_driver_resolves_async_input_and_output_pipeline_values(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, pipe_output, source, step, value

async def add(value: int, amount: int) -> int:
    await asyncio.sleep(0)
    return value + amount

@pipe_input(step(add, amount=value(2)), namespace="input")
async def input_value(value: int) -> int:
    await asyncio.sleep(0)
    return value * 3

@pipe_output(step(add, amount=source("offset")), namespace="output")
async def output_value(value: int, offset: int) -> int:
    await asyncio.sleep(0)
    return value * 3

def result(input_value: int, output_value: int) -> int:
    return input_value + output_value
""",
        asyncio=asyncio,
    )

    assert await Driver(module).prepare(["result"]).execute(inputs={"value": 2, "offset": 4}) == {
        "result": 22
    }


@pytest.mark.asyncio
async def test_driver_executes_does_with_original_defaults_and_typed_replacement(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import does

def replacement(number: int, offset: int = 2) -> int:
    return number + offset

@does(replacement)
def replaced(number: int, offset: int = 2) -> int:
    pass

def result(replaced: int) -> int:
    return replaced * 2
""")

    plan = Driver(module).prepare(["result"])
    assert plan.required_inputs == {"number": (int,)}
    assert await plan.execute(inputs={"number": 3}) == {"result": 10}


@pytest.mark.asyncio
async def test_driver_captures_import_time_mutate_on_its_target(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import mutate, value

def target(value: int) -> int:
    return value * 2

@mutate(target, amount=value(3))
def add(value: int, amount: int) -> int:
    return value + amount

def result(target: int) -> int:
    return target
""")

    assert await Driver(module).prepare(["result"]).execute(inputs={"value": 2}) == {"result": 7}


@pytest.mark.asyncio
async def test_existing_driver_plan_ignores_later_pipeline_binding_and_helper_code_mutation(
    module_factory,
):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step, value

def add(value: int, amount: int = 1) -> int:
    return value + amount

@pipe_output(step(add, amount=value(2)))
def result(value: int) -> int:
    return value

def changed(value: int, amount: int = 99) -> int:
    return value + amount + 100
""")
    plan = Driver(module).prepare(["result"])

    module.result.transform[0].transforms[0].kwargs["amount"] = value(50)
    module.add.__code__ = module.changed.__code__
    module.add.__defaults__ = module.changed.__defaults__

    assert await plan.execute(inputs={"value": 3}) == {"result": 5}


@pytest.mark.asyncio
async def test_existing_driver_plan_ignores_later_does_replacement_code_mutation(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import does

def replacement(number: int, offset: int = 2) -> int:
    return number + offset

@does(replacement)
def result(number: int, offset: int = 2) -> int:
    pass

def changed(number: int, offset: int = 99) -> int:
    return number + offset + 100
""")
    plan = Driver(module).prepare(["result"])

    module.replacement.__code__ = module.changed.__code__
    module.replacement.__defaults__ = module.changed.__defaults__

    assert await plan.execute(inputs={"number": 3}) == {"result": 5}


@pytest.mark.asyncio
async def test_direct_and_generated_helper_calls_keep_distinct_shutdowns_after_mutation(
    module_factory,
):
    events: list[tuple[str, int]] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
from sdax_hamilton import Acquisition, shutdown

def helper(value: int) -> int:
    events.append(("helper", value))
    return value + 1

@shutdown(of=helper)
def close_helper(state: Acquisition[int]) -> None:
    events.append(("close-helper", state.value))

@pipe_output(step(helper))
def resource() -> int:
    events.append(("resource", 3))
    return 3

@shutdown(of=resource, target_="resource.raw")
def close_resource(state: Acquisition[int]) -> None:
    events.append(("close-resource", state.value))

def changed(value: int = 99) -> int:
    raise AssertionError("mutated helper code ran")

def changed_close(state: int) -> None:
    raise AssertionError("mutated shutdown ran")
""",
        events=events,
    )
    plan = Driver(module).prepare(["helper", "resource"])

    module.resource.transform[0].transforms = ()
    module.helper.__code__ = module.changed.__code__
    module.helper.__defaults__ = module.changed.__defaults__
    module.close_helper.__code__ = module.changed_close.__code__
    module.close_resource.__code__ = module.changed_close.__code__

    async with plan.open(inputs={"value": 2}) as values:
        assert values == {"helper": 3, "resource": 4}
        assert events == [("helper", 2), ("resource", 3), ("helper", 3)]
    assert sorted(events[3:]) == [
        ("close-helper", 3),
        ("close-helper", 4),
        ("close-resource", 3),
    ]


@pytest.mark.asyncio
async def test_generated_pipeline_helper_default_is_retained_after_hamilton_renames_input(
    module_factory,
):
    module = module_factory("""
from hamilton.function_modifiers import pipe_output, step

def increment(value: int = 2) -> int:
    return value + 1

@pipe_output(step(increment))
def result() -> int:
    return 3
""")

    plan = Driver(module).prepare(["result"])
    assert plan.required_inputs == {}
    assert await plan.execute() == {"result": 4}


@pytest.mark.asyncio
async def test_pipeline_preserves_both_original_requirements_for_one_merged_external_input(
    module_factory,
):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, source, step

def helper(a: str, b: int) -> int:
    events.append("helper")
    return b

@pipe_input(step(helper, b=source("value")))
def result(value: int) -> int:
    events.append("result")
    return 0
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"], check_outputs=False)

    # Hamilton's generated helper has one ``value`` input whose declared type
    # is the last merged argument's ``int``. SDAX must retain the earlier
    # ``a: str`` requirement too, before any helper callback can run.
    assert plan.required_inputs == {"value": (str, int)}
    with pytest.raises(TypeError, match="Invalid input: value"):
        await plan.execute(inputs={"value": 1})
    assert events == []


@pytest.mark.asyncio
async def test_pipeline_preserves_both_original_requirements_for_one_merged_override(
    module_factory,
):
    events: list[str] = []
    module = module_factory(
        """
from typing import Any

from hamilton.function_modifiers import pipe_input, source, step

def value() -> Any:
    events.append("source")
    return 1

def helper(a: str, b: int) -> int:
    events.append("helper")
    return b

@pipe_input(step(helper, b=source("value")))
def result(value: int) -> int:
    events.append("result")
    return 0
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"], override_nodes=["value"], check_outputs=False)

    with pytest.raises(TypeError, match="Invalid override: value"):
        await plan.execute(overrides={"value": 1})
    assert events == []


@pytest.mark.asyncio
async def test_pipeline_merged_required_then_optional_source_stays_required(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, source, step

def helper(required: int, optional: int = 2) -> int:
    events.append("helper")
    return required + optional

@pipe_input(step(helper, optional=source("value")))
def result(value: int) -> int:
    events.append("result")
    return value
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"], check_outputs=False)

    assert plan.required_inputs == {"value": (int, int)}
    with pytest.raises(ValueError, match="Input shape mismatch"):
        await plan.execute()
    assert events == []


@pytest.mark.asyncio
async def test_pipeline_merged_optional_then_required_source_stays_required(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_input, source, step

def helper(optional: int = 2, *, required: int) -> int:
    events.append("helper")
    return optional + required

@pipe_input(step(helper, required=source("value")))
def result(value: int) -> int:
    events.append("result")
    return value
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"], check_outputs=False)

    assert plan.required_inputs == {"value": (int, int)}
    with pytest.raises(ValueError, match="Input shape mismatch"):
        await plan.execute()
    assert events == []


def test_pipeline_merged_optional_sources_keep_an_identical_default(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_input, source, step

default = [2]

def helper(first: list[int] = default, *, second: list[int] = default) -> list[int]:
    return first + second

@pipe_input(step(helper, second=source("value")))
def result(value: list[int]) -> list[int]:
    return value
""")

    plan = Driver(module).prepare(["result"])

    assert plan.required_inputs == {}


def test_pipeline_rejects_conflicting_merged_optional_source_defaults(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import pipe_input, source, step

def helper(first: list[int] = [2], *, second: list[int] = [3]) -> list[int]:
    return first + second

@pipe_input(step(helper, second=source("value")))
def result(value: list[int]) -> list[int]:
    return value
""")

    with pytest.raises(ValueError, match="conflicting merged source defaults"):
        Driver(module)


@pytest.mark.asyncio
async def test_pipeline_captured_requirement_blocks_helper_but_releases_raw_acquisition(
    module_factory,
):
    events: list[object] = []
    module = module_factory(
        """
from typing import Any

from hamilton.function_modifiers import pipe_output, step
from sdax_hamilton import Acquisition, shutdown

def helper(value: int) -> int:
    events.append("helper")
    return value + 1

@pipe_output(step(helper))
def resource() -> Any:
    events.append("resource")
    return "wrong"

@shutdown(of=resource, target_="resource.raw")
def close_resource(state: Acquisition[Any]) -> None:
    events.append(("close", state.value))

def result(resource: int) -> int:
    events.append("result")
    return resource
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"], check_outputs=False)

    with pytest.raises(BaseExceptionGroup):
        await plan.execute()
    assert events == ["resource", ("close", "wrong")]


@pytest.mark.asyncio
async def test_async_selected_pipeline_step_skips_invalid_conditional_literal(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step, value

def invalid(value: int, offset: int) -> int:
    return value + offset

async def increment(value: int, offset: int) -> int:
    await asyncio.sleep(0)
    return value + offset

@pipe_output(
    step(invalid, offset=value("wrong")).when(mode="unsafe"),
    step(increment, offset=value(2)).when(mode="safe"),
)
async def result(value: int) -> int:
    await asyncio.sleep(0)
    return value
""",
        asyncio=asyncio,
    )

    safe = Driver(module, config={"mode": "safe"}).prepare(["result"])
    assert await safe.execute(inputs={"value": 3}) == {"result": 5}
    with pytest.raises(TypeError, match="bound literal has wrong type"):
        Driver(module, config={"mode": "unsafe"})


@pytest.mark.parametrize(
    "source, message",
    [
        (
            """
from hamilton.function_modifiers import pipe_input, step, value

def add(value: int, amount: int) -> int:
    return value + amount

@pipe_input(step(add, amount=value("wrong")))
def result(value: int) -> int:
    return value
""",
            "literal",
        ),
        (
            """
from hamilton.function_modifiers import does

def replacement(number: str) -> int:
    return len(number)

@does(replacement)
def result(number: int) -> int:
    pass
""",
            "replacement",
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
            "replacement return",
        ),
        (
            """
from hamilton.function_modifiers import pipe_input, step

def add(value: str) -> str:
    return value

@pipe_input(step(add))
def result(value: int) -> int:
    return value
            """,
            "expecting",
        ),
    ],
)
def test_driver_rejects_invalid_c_macro_binding_contracts(module_factory, source, message):
    with pytest.raises((TypeError, ValueError), match=message):
        Driver(module_factory(source))


def test_driver_rejects_unknown_pipeline_selector_before_expansion(module_factory):
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

    with pytest.raises(ValueError, match="configuration selector"):
        Driver(module)


@pytest.mark.asyncio
async def test_output_pipeline_raw_node_is_the_owned_policy_and_shutdown_target(module_factory):
    events: list[int] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
from sdax_hamilton import Acquisition, execution, shutdown

def add(value: int) -> int:
    return value + 1

@execution(target_="resource.raw", timeout=2)
@pipe_output(step(add))
def resource() -> int:
    return 2

@shutdown(of=resource, target_="resource.raw")
def close(state: Acquisition[int]) -> None:
    events.append(state.value)

def result(resource: int) -> int:
    return resource * 3
""",
        events=events,
    )

    plan = Driver(module).prepare(["result"])
    raw = plan._selection.nodes["resource.raw"]
    final = plan._selection.nodes["resource"]
    assert raw.policy.timeout == 2
    assert raw.release is not None
    assert final.policy.timeout is None
    assert final.release is None
    assert final.borrow_from == frozenset({"resource.raw"})  # type: ignore[attr-defined]
    with pytest.raises(ValueError, match="borrowed"):
        Driver(module).prepare(["result"], override_nodes=["resource"])
    assert await plan.execute() == {"result": 9}
    assert events == [2]
