"""Public compiler contracts using installed Hamilton, not the private campaign."""

import asyncio

import pytest

from sdax_hamilton import Driver


@pytest.mark.asyncio
async def test_real_decorators_execute_sync_and_async(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import inject, parameterize, source, tag, value
@parameterize(left={"x": source("seed")}, right={"x": value(4)})
async def times(x: int) -> int:
    return x * 2
@tag(category="example")
@inject(offset=value(3))
def result(left: int, right: int, offset: int) -> int:
    return left + right + offset
""")
    plan = Driver(module).prepare(["result"])
    assert await plan.execute(inputs={"seed": 5}) == {"result": 21}


@pytest.mark.asyncio
async def test_stock_hamilton_parity_and_config_isolation(module_factory):
    from hamilton import driver as stock

    source = """
from hamilton.function_modifiers import config, inject, parameterize, source, value
@config.when(which="a")
def seed__a() -> int:
    return 2
@config.when(which="b")
def seed__b() -> int:
    return 5
@parameterize(left={"x": source("seed")}, right={"x": value(3)})
def twice(x: int) -> int:
    return x * 2
@inject(extra=value(1))
def result(left: int, right: int, extra: int) -> int:
    return left + right + extra
"""
    module = module_factory(source)
    for choice in ("a", "b", "a"):
        configuration = {"which": choice}
        frontend = Driver(module, config=configuration)
        configuration["which"] = "changed after construction"
        expected = (
            stock.Builder()
            .with_modules(module_factory(source))
            .with_config({"which": choice})
            .build()
            .execute(["result"])
        )
        assert await frontend.prepare(["result"]).execute() == expected
        assert module.seed__a.__name__ == "seed__a"
        assert module.seed__b.__name__ == "seed__b"


@pytest.mark.parametrize(
    "decorator",
    [
        'config.when(which="a")',
        'config.when_not(which="b")',
        'config.when_in(which=["a", "c"])',
        'config.when_not_in(which=["b", "c"])',
    ],
)
@pytest.mark.asyncio
async def test_config_selection_family(module_factory, decorator):
    module = module_factory(f"""
from hamilton.function_modifiers import config
@{decorator}
def result__chosen() -> int:
    return 7
""")
    assert await Driver(module, config={"which": "a"}).prepare(["result"]).execute() == {
        "result": 7
    }


@pytest.mark.parametrize(
    "source, message",
    [
        ("def result(x) -> int:\n    return x", "missing type"),
        ("def result(x: int):\n    return x", "missing return type"),
        ('def result(x: int = "wrong") -> int:\n    return x', "invalid default"),
        ("def result(x: int, /) -> int:\n    return x", "positional-only"),
        ("def result(*x: int) -> int:\n    return 1", "variadic"),
        (
            'from typing import Annotated\ndef result(x: Annotated[int, "units"]) -> int:\n    return x',
            "Unsupported annotation",
        ),
        (
            """from hamilton.function_modifiers import inject, value
@inject(x=value("wrong"))
def result(x: int) -> int:
    return x""",
            "bound literal",
        ),
        (
            """from hamilton.function_modifiers import inject, source
@inject(x=source("former_inputs"))
def result(x: int) -> int:
    return x""",
            "collides with Hamilton wrapper",
        ),
        (
            """from hamilton.function_modifiers import extract_fields
@extract_fields({"field": int})
def result() -> dict:
    return {"field": 1}""",
            "unsupported Hamilton decorator",
        ),
    ],
)
def test_declarations_reject_before_execution(module_factory, source, message):
    with pytest.raises((TypeError, ValueError), match=message):
        Driver(module_factory(source))


@pytest.mark.parametrize(
    "shutdown_definition, message",
    [
        ("def close(state: Acquisition[int] = None) -> None:\n    pass", "required positional"),
        ("def close(*, state: Acquisition[int]) -> None:\n    pass", "required positional"),
        ("def close(state: int) -> None:\n    pass", "Acquisition"),
        ("def close(state: Acquisition[str]) -> None:\n    pass", "does not accept"),
        ("def close(state: Acquisition[int]) -> int:\n    return 1", "return None"),
    ],
)
def test_shutdown_contract_rejected(module_factory, shutdown_definition, message):
    module = module_factory(
        """
from sdax_hamilton import Acquisition, execution, shutdown
def owner() -> int:
    return 1
@shutdown(of=owner)
"""
        + shutdown_definition
    )
    with pytest.raises((TypeError, ValueError), match=message):
        Driver(module)


def test_conflicting_declarations_rejected_at_definition(module_factory):
    with pytest.raises(ValueError, match="Conflicting"):
        module_factory("""
from sdax_hamilton import Acquisition, execution, shutdown
def owner() -> int:
    return 1
@shutdown(of=owner)
@execution(timeout=1)
def close(state: Acquisition[int]) -> None:
    pass
""")


@pytest.mark.asyncio
async def test_parameterized_ownership_and_tuple_targets(module_factory):
    released = []
    module = module_factory(
        """
from hamilton.function_modifiers import parameterize, value
from sdax_hamilton import Acquisition, execution, shutdown
@execution(target_=("left", "right"), timeout=1)
@parameterize(left={"number": value(1)}, right={"number": value(2)})
async def owner(number: int) -> int:
    return number
@shutdown(of=owner, target_=("left", "right"))
def close(state: Acquisition[int]) -> None:
    released.append(state.value)
def result(left: int, right: int) -> int:
    return left + right
""",
        released=released,
    )
    assert await Driver(module).prepare(["result"]).execute() == {"result": 3}
    assert sorted(released) == [1, 2]


def test_selected_unowned_sibling_cannot_escape_ownership(module_factory):
    module = module_factory("""
from hamilton.function_modifiers import parameterize, value
from sdax_hamilton import Acquisition, shutdown
@parameterize(left={"number": value(1)}, right={"number": value(2)})
def owner(number: int) -> int:
    return number
@shutdown(of=owner, target_="left")
def close(state: Acquisition[int]) -> None:
    pass
""")
    driver = Driver(module)
    driver.prepare(["left"])
    with pytest.raises(ValueError):
        driver.prepare(["right"])
    for name in ("left", "right"):
        with pytest.raises(ValueError):
            driver.prepare([name], override_nodes=[name])
        with pytest.raises(ValueError):
            Driver(module, config={name: 3}).prepare([name])


@pytest.mark.parametrize("target", ["None", '"unknown"'])
def test_ambiguous_or_missing_expansion_target(module_factory, target):
    module = module_factory(f"""
from hamilton.function_modifiers import parameterize, value
from sdax_hamilton import execution
@execution(target_={target}, timeout=1)
@parameterize(left={{"x": value(1)}}, right={{"x": value(2)}})
def owner(x: int) -> int:
    return x
""")
    with pytest.raises(ValueError, match="target"):
        Driver(module)


def test_duplicate_shutdown_and_node_names(module_factory):
    module = module_factory("""
from sdax_hamilton import Acquisition, shutdown
def owner() -> int:
    return 1
@shutdown(of=owner)
def first(state: Acquisition[int]) -> None:
    pass
@shutdown(of=owner)
def second(state: Acquisition[int]) -> None:
    pass
""")
    with pytest.raises(ValueError, match="duplicate shutdown"):
        Driver(module)
    a = module_factory("def result() -> int:\n    return 1")
    b = module_factory("def result() -> int:\n    return 2")
    with pytest.raises(ValueError, match="Duplicate Hamilton node"):
        Driver(a, b)


@pytest.mark.asyncio
async def test_compile_once_and_does_not_export_mutable_graph(module_factory, monkeypatch):
    from sdax_hamilton import hamilton_compat

    calls = []
    original = hamilton_compat.base.resolve_nodes

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(hamilton_compat.base, "resolve_nodes", counted)
    module = module_factory("def result(seed: int) -> int:\n    return seed + 1")
    driver = Driver(module, module)
    plans = [driver.prepare(["result"]) for _ in range(2)]
    assert await asyncio.gather(
        *(plan.execute(inputs={"seed": i}) for i, plan in enumerate(plans))
    ) == [{"result": 1}, {"result": 2}]
    assert calls == [1]
    assert not hasattr(driver, "nodes") and not hasattr(driver, "hamilton_nodes")
    with pytest.raises(TypeError):
        driver._nodes["new"] = None


@pytest.mark.parametrize("version_source", ["distribution", "imported"])
def test_version_boundary_fails_closed(module_factory, monkeypatch, version_source):
    from sdax_hamilton import hamilton_compat

    if version_source == "distribution":
        monkeypatch.setattr(hamilton_compat.metadata, "version", lambda _: "1.91.0")
    else:
        monkeypatch.setattr(hamilton_compat.hamilton, "__version__", (1, 91, 0))
    with pytest.raises(RuntimeError, match="Unsupported Hamilton version"):
        Driver(module_factory("def result() -> int:\n    return 1"))


@pytest.mark.asyncio
async def test_decorator_binding_metadata_is_snapshotted(module_factory):
    from hamilton.function_modifiers import source

    binding = source("seed")
    module = module_factory(
        """
from hamilton.function_modifiers import inject
@inject(x=binding)
def result(x: int) -> int:
    return x
""",
        binding=binding,
    )
    driver = Driver(module)
    binding.source = "changed_after_compilation"
    assert await driver.prepare(["result"]).execute(inputs={"seed": 3}) == {"result": 3}


@pytest.mark.parametrize("async_prefix", ["", "async "])
@pytest.mark.parametrize("shutdown", [False, True])
def test_generator_forms_rejected_before_acquisition(module_factory, async_prefix, shutdown):
    events = []
    if shutdown:
        source = f"""
from sdax_hamilton import Acquisition, shutdown
def owner() -> int:
    events.append("acquired")
    return 1
@shutdown(of=owner)
{async_prefix}def close(state: Acquisition[int]) -> None:
    events.append("released")
    yield
"""
    else:
        source = f"""
{async_prefix}def result() -> int:
    events.append("called")
    yield 1
"""
    with pytest.raises(TypeError, match="generator"):
        Driver(module_factory(source, events=events))
    assert events == []


@pytest.mark.asyncio
async def test_shutdown_function_snapshot_isolated_from_code_mutation(module_factory):
    events = []
    module = module_factory(
        """
from sdax_hamilton import Acquisition, shutdown
def owner() -> int:
    return 1
@shutdown(of=owner)
def close(state: Acquisition[int]) -> None:
    events.append("original")
def result(owner: int) -> int:
    return owner
""",
        events=events,
    )
    plan = Driver(module).prepare(["result"])

    def replacement(state):
        raise AssertionError("A mutated declaration changed existing cleanup")

    module.close.__code__ = replacement.__code__
    assert await plan.execute() == {"result": 1}
    assert events == ["original"]


def test_sdax_version_boundary_fails_closed(module_factory, monkeypatch):
    from sdax_hamilton import hamilton_compat

    original_version = hamilton_compat.metadata.version
    monkeypatch.setattr(
        hamilton_compat.metadata,
        "version",
        lambda name: "0.8.0" if name == "sdax" else original_version(name),
    )
    with pytest.raises(RuntimeError, match="Unsupported SDAX version"):
        Driver(module_factory("def result() -> int:\n    return 1"))
