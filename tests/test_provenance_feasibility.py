"""Bounded proof that production compilation preserves generated-node provenance."""

import gc
import inspect
import weakref
from collections import Counter
from collections.abc import Callable
from typing import Any, get_type_hints

import pytest
from hamilton import driver as hamilton_driver
from hamilton import settings
from hamilton.data_quality import base as data_quality
from hamilton.function_modifiers import base, parameterized_subdag
from hamilton.function_modifiers.delayed import resolve_from_config
from hamilton.function_modifiers.expanders import extract_fields

from sdax_hamilton import Acquisition, Driver, hamilton_compat, shutdown
from sdax_hamilton._model import GeneratedRole
from sdax_hamilton.plan import PreparedPlan


class Handle:
    def __init__(self, number: int, events: list[tuple[str, int]]) -> None:
        self.number = number
        self.events = events
        self.live = True


class MinimumValidator(data_quality.DataValidator):
    def __init__(self, minimum: int) -> None:
        super().__init__("fail")
        self.minimum = minimum

    @classmethod
    def name(cls) -> str:
        return "minimum"

    def applies_to(self, datatype: type[type]) -> bool:
        return datatype is int

    def description(self) -> str:
        return "value meets the configured minimum"

    def validate(self, dataset: Any) -> data_quality.ValidationResult:
        return data_quality.ValidationResult(
            passes=dataset >= self.minimum,
            message="minimum check",
            diagnostics={},
        )


def _make_fixture(module_factory, minimums: tuple[int, int]):
    events: list[tuple[str, int]] = []
    resolver_calls: list[int] = []

    def make_check(configured_minimum: int):
        from hamilton.function_modifiers import check_output_custom

        resolver_calls.append(configured_minimum)
        return check_output_custom(MinimumValidator(configured_minimum))

    component = module_factory(
        """
from hamilton.function_modifiers import extract_fields, resolve_from_config

def acquire(token: int) -> Handle:
    events.append(("acquire", token))
    return Handle(token, events)

@extract_fields({"number": int})
def projected(acquire: Handle) -> dict[str, int]:
    assert acquire.live
    return {"number": acquire.number}

@resolve_from_config(decorate_with=make_check)
def checked(number: int) -> int:
    return number
""",
        Handle=Handle,
        events=events,
        make_check=make_check,
    )
    mounted = module_factory(
        """
from hamilton.function_modifiers import parameterized_subdag, value
from sdax_hamilton import Acquisition, shutdown

@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    handle = state.value
    assert handle.live
    handle.live = False
    events.append(("release", handle.number))

@parameterized_subdag(
    acquire,
    projected,
    checked,
    low={
        "inputs": {"token": value(2)},
        "config": {"configured_minimum": low_minimum},
    },
    high={
        "inputs": {"token": value(5)},
        "config": {"configured_minimum": high_minimum},
    },
)
def result(checked: int) -> int:
    return checked
""",
        Acquisition=Acquisition,
        Handle=Handle,
        acquire=component.acquire,
        checked=component.checked,
        events=events,
        high_minimum=minimums[1],
        low_minimum=minimums[0],
        projected=component.projected,
        shutdown=shutdown,
    )
    configuration = {
        settings.ENABLE_POWER_USER_MODE: True,
    }
    return component, mounted, configuration, events, resolver_calls


def _decorator_objects(fn: Callable[..., Any]) -> tuple[object, ...]:
    return tuple(
        modifier
        for stage in hamilton_compat._LIFECYCLES
        for modifier in getattr(fn, stage.get_lifecycle_name(), ())
    )


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in _leaves(child)]
    return [error]


def _compile_with_capture_observer(monkeypatch, mounted, configuration):
    capture_refs = []
    capture_class = hamilton_compat._ProvenanceCapture

    class ObservedCapture(capture_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            capture_refs.append(weakref.ref(self))

    monkeypatch.setattr(hamilton_compat, "_ProvenanceCapture", ObservedCapture)
    specs = hamilton_compat.compile_modules(
        (mounted,),
        configuration,
        _supported=(
            *hamilton_compat._SUPPORTED,
            extract_fields,
            parameterized_subdag,
            resolve_from_config,
        ),
    )
    return specs, capture_refs


@pytest.mark.asyncio
async def test_projection_borrows_owner_across_declaration_roots(module_factory):
    events = []
    module = module_factory(
        """
from hamilton.function_modifiers import extract_fields
from sdax_hamilton import Acquisition, shutdown

def acquire() -> Handle:
    events.append(("acquire", 7))
    return Handle(7, events)

@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    state.value.live = False
    events.append(("release", state.value.number))

@extract_fields({"number": int})
def projected(acquire: Handle) -> dict[str, int]:
    assert acquire.live
    return {"number": acquire.number}
""",
        Acquisition=Acquisition,
        Handle=Handle,
        events=events,
        shutdown=shutdown,
    )
    specs = hamilton_compat.compile_modules(
        (module,),
        {},
        _supported=(*hamilton_compat._SUPPORTED, extract_fields),
    )

    assert specs["number"].role is GeneratedRole.PROJECTION
    assert specs["number"].borrow_from == frozenset({"acquire"})
    assert await PreparedPlan(specs, ["number"]).execute() == {"number": 7}
    assert events == [("acquire", 7), ("release", 7)]


def test_nested_mount_hands_roles_to_each_parent_without_name_collisions(module_factory):
    first_component, first_mounted, configuration, _, first_calls = _make_fixture(
        module_factory, (1, 3)
    )
    second_component, second_mounted, _, _, second_calls = _make_fixture(
        module_factory, (2, 4)
    )
    outer_source = """
from hamilton.function_modifiers import parameterized_subdag
from sdax_hamilton import Acquisition, shutdown

@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    state.value.live = False

@parameterized_subdag(result, NAMESPACE={})
def outer(low: int) -> int:
    return low
"""
    left = module_factory(
        outer_source.replace("NAMESPACE", "left"),
        Acquisition=Acquisition,
        Handle=Handle,
        acquire=first_component.acquire,
        result=first_mounted.result,
        shutdown=shutdown,
    )
    right = module_factory(
        outer_source.replace("NAMESPACE", "right"),
        Acquisition=Acquisition,
        Handle=Handle,
        acquire=second_component.acquire,
        result=second_mounted.result,
        shutdown=shutdown,
    )
    specs = hamilton_compat.compile_modules(
        (left, right),
        configuration,
        _supported=(
            *hamilton_compat._SUPPORTED,
            extract_fields,
            parameterized_subdag,
            resolve_from_config,
        ),
    )

    assert specs["left.low.number"].role is GeneratedRole.PROJECTION
    assert specs["left.low.number"].borrow_from == frozenset({"left.low.acquire"})
    assert specs["right.low.number"].role is GeneratedRole.PROJECTION
    assert specs["right.low.number"].borrow_from == frozenset({"right.low.acquire"})
    assert specs["left.low.number"].origin != specs["right.low.number"].origin
    assert specs["left.low.acquire"].ownership_required
    assert specs["right.low.acquire"].ownership_required
    assert not specs["left.low.number"].ownership_required
    assert not specs["right.low.number"].ownership_required
    assert Counter(first_calls) == Counter({1: 1, 3: 1})
    assert Counter(second_calls) == Counter({2: 1, 4: 1})


def test_capture_is_discarded_after_construction_failure(module_factory, monkeypatch, caplog):
    calls = []

    class Sentinel(RuntimeError):
        pass

    def explode():
        error = Sentinel("private sentinel")
        calls.append(id(error))
        raise error

    module = module_factory(
        """
from hamilton.function_modifiers import resolve_from_config

@resolve_from_config(decorate_with=explode)
def result(value: int) -> int:
    return value
""",
        explode=explode,
    )
    original_decorators = _decorator_objects(module.result)
    capture_refs = []
    capture_class = hamilton_compat._ProvenanceCapture

    class ObservedCapture(capture_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            capture_refs.append(weakref.ref(self))

    monkeypatch.setattr(hamilton_compat, "_ProvenanceCapture", ObservedCapture)

    def construct() -> None:
        with pytest.raises(RuntimeError) as result:
            hamilton_compat.compile_modules(
                (module,),
                {settings.ENABLE_POWER_USER_MODE: True},
                _supported=(*hamilton_compat._SUPPORTED, resolve_from_config),
            )
        assert type(result.value) is Sentinel
        assert id(result.value) == calls[0]
        assert result.value.__context__ is None
        assert result.value.__cause__ is None

    construct()
    gc.collect()
    assert len(calls) == 1
    assert not [
        record
        for record in caplog.records
        if record.name == "hamilton.function_modifiers.base"
    ]
    assert _decorator_objects(module.result) == original_decorators
    assert len(capture_refs) == 1
    assert capture_refs[0]() is None


@pytest.mark.asyncio
async def test_production_capture_preserves_mounted_roles_once(
    module_factory, graph_signature, monkeypatch
):
    stable = Driver(module_factory("def stable(value: int) -> int:\n    return value + 1")).prepare(
        ["stable"]
    )
    component, mounted, configuration, events, resolver_calls = _make_fixture(
        module_factory, (1, 3)
    )
    originals = {
        fn: _decorator_objects(fn)
        for fn in (component.acquire, component.projected, component.checked, mounted.result)
    }
    resolve_nodes = base.resolve_nodes

    with pytest.raises(ValueError, match="unsupported Hamilton decorator parameterized_subdag"):
        Driver(mounted, config=configuration)

    specs, capture_refs = _compile_with_capture_observer(monkeypatch, mounted, configuration)
    assert Counter(resolver_calls) == Counter({1: 1, 3: 1})

    stock_component, stock_mounted, stock_config, _, stock_resolver_calls = _make_fixture(
        module_factory, (1, 3)
    )
    stock_nodes = {entry.name: entry for entry in base.resolve_nodes(stock_mounted.result, stock_config)}
    assert graph_signature(specs) == graph_signature(stock_nodes)
    assert Counter(stock_resolver_calls) == Counter({1: 1, 3: 1})

    expected_roles = {
        "acquire": GeneratedRole.VALUE,
        "projected": GeneratedRole.VALUE,
        "number": GeneratedRole.PROJECTION,
        "checked_raw": GeneratedRole.VALIDATION_RAW,
        "checked_minimum": GeneratedRole.VALIDATION_EVIDENCE,
        "checked": GeneratedRole.VALIDATION_GATE,
    }
    for mount in ("low", "high"):
        assert {
            name: specs[f"{mount}.{name}"].role for name in expected_roles
        } == expected_roles
        assert specs[f"{mount}.acquire"].ownership_required
        assert specs[f"{mount}.acquire"].release is not None
        for name in ("number", "checked_raw", "checked"):
            assert specs[f"{mount}.{name}"].borrow_from == frozenset(
                {f"{mount}.acquire"}
            )
        assert not specs[f"{mount}.checked_minimum"].borrow_from

    stock_checked = {
        name: entry.originating_functions
        for name, entry in stock_nodes.items()
        if name in {"low.checked_raw", "low.checked_minimum", "low.checked"}
    }
    assert len(set(stock_checked.values())) == 1
    assert inspect.signature(component.checked).parameters["number"].annotation is int
    assert get_type_hints(component.acquire)["return"] is Handle

    plan = PreparedPlan(specs, ["low", "high"])
    assert await plan.execute() == {"low": 2, "high": 5}
    assert Counter(resolver_calls) == Counter({1: 1, 3: 1})
    assert Counter(events) == Counter(
        {("acquire", 2): 1, ("release", 2): 1, ("acquire", 5): 1, ("release", 5): 1}
    )

    oracle_component, oracle_mounted, oracle_config, _, oracle_resolver_calls = _make_fixture(
        module_factory, (1, 3)
    )
    oracle = (
        hamilton_driver.Builder()
        .with_modules(oracle_mounted)
        .with_config(oracle_config)
        .build()
    )
    assert oracle.execute(["low", "high"]) == {"low": 2, "high": 5}
    assert Counter(oracle_resolver_calls) == Counter({1: 1, 3: 1})
    assert oracle_component.acquire is not component.acquire

    assert base.resolve_nodes is resolve_nodes
    for fn, decorators in originals.items():
        assert _decorator_objects(fn) == decorators
    assert "_gather_subdag_generators" not in originals[mounted.result][0].__dict__
    assert await stable.execute(inputs={"value": 6}) == {"stable": 7}

    gc.collect()
    assert len(capture_refs) == 1
    assert capture_refs[0]() is None


@pytest.mark.asyncio
async def test_validation_failure_releases_each_actual_mount_once(module_factory, monkeypatch):
    _, mounted, configuration, events, resolver_calls = _make_fixture(module_factory, (4, 6))
    specs, capture_refs = _compile_with_capture_observer(monkeypatch, mounted, configuration)
    plan = PreparedPlan(specs, ["low", "high"])

    with pytest.raises(BaseExceptionGroup) as result:
        await plan.execute()

    assert any(isinstance(error, data_quality.DataValidationError) for error in _leaves(result.value))
    assert Counter(resolver_calls) == Counter({4: 1, 6: 1})
    assert Counter(events) == Counter(
        {("acquire", 2): 1, ("release", 2): 1, ("acquire", 5): 1, ("release", 5): 1}
    )
    gc.collect()
    assert capture_refs[0]() is None
