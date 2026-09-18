"""Bounded proof that production compilation preserves generated-node provenance."""

import asyncio
import gc
import inspect
import logging
import weakref
from collections import Counter
from collections.abc import Callable
from types import MappingProxyType
from typing import Any, get_type_hints

import pytest
from hamilton import driver as hamilton_driver
from hamilton import node, settings
from hamilton.data_quality import base as data_quality
from hamilton.function_modifiers import base, parameterized_subdag
from hamilton.function_modifiers.delayed import resolve_from_config
from hamilton.function_modifiers.expanders import extract_fields
from hamilton.function_modifiers.macros import does, pipe_output
from hamilton.function_modifiers.validation import check_output_custom

from sdax_hamilton import Acquisition, Driver, hamilton_compat, shutdown
from sdax_hamilton._hamilton_provenance import _CapturedFact, _ProvenanceCapture
from sdax_hamilton._model import GeneratedRole, InputSpec
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
            check_output_custom,
        ),
    )
    return specs, capture_refs


def test_input_contract_namespace_handoff_preserves_exact_edge_order():
    def call(**kwargs):
        return kwargs

    required = node.DependencyType.REQUIRED
    before = node.Node(
        "value",
        int,
        callabl=call,
        input_types={"number": (int, required), "label": (str, required)},
    )
    after = node.Node(
        "mounted.value",
        int,
        callabl=call,
        input_types={
            "mounted.number": (int, required),
            "mounted.label": (str, required),
        },
    )
    mount = object()
    fact = _CapturedFact(
        GeneratedRole.VALUE,
        call,
        True,
        False,
        "value",
        object(),
        MappingProxyType(
            {
                "number": InputSpec(int, requirements=(int,)),
                "label": InputSpec(str, requirements=(str,)),
            }
        ),
    )
    capture = _ProvenanceCapture((), ())
    capture._handoff(after, mount, fact, before=before)
    capture._mounts.append((mount, ("mounted",)))

    remapped = capture.fact(after).input_contracts
    assert tuple(remapped) == ("mounted.number", "mounted.label")
    assert remapped["mounted.number"].effective_requirements == (int,)
    assert remapped["mounted.label"].effective_requirements == (str,)

    reordered = node.Node(
        "mounted.value",
        int,
        callabl=call,
        input_types={
            "mounted.label": (str, required),
            "mounted.number": (int, required),
        },
    )
    with pytest.raises(AssertionError, match="reordered captured inputs"):
        capture._handoff(reordered, mount, fact, before=before)


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
    async with PreparedPlan(specs, ["number"]).open() as result:
        assert result == {"number": 7}
        assert events == [("acquire", 7)]
    assert events == [("acquire", 7), ("release", 7)]



@pytest.mark.asyncio
async def test_cancellation_through_projection_releases_borrowed_owner_once(module_factory):
    events = []
    started = asyncio.Event()
    module = module_factory(
        """
from hamilton.function_modifiers import extract_fields
from sdax_hamilton import Acquisition, shutdown

def acquire() -> Handle:
    events.append(("acquire", 7))
    return Handle(7, events)

@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    assert state.has_value and state.value.live
    state.value.live = False
    events.append(("release", state.value.number))

@extract_fields({"number": int})
def projected(acquire: Handle) -> dict[str, int]:
    assert acquire.live
    return {"number": acquire.number}

async def waiting(number: int) -> int:
    started.set()
    await asyncio.Event().wait()
    return number
""",
        asyncio=asyncio,
        Handle=Handle,
        events=events,
        started=started,
    )
    specs = hamilton_compat.compile_modules(
        (module,), {}, _supported=(*hamilton_compat._SUPPORTED, extract_fields)
    )
    assert specs["number"].borrow_from == frozenset({"acquire"})
    job = asyncio.create_task(PreparedPlan(specs, ["waiting"]).execute())
    try:
        await asyncio.wait_for(started.wait(), 1)
        assert events == [("acquire", 7)]
        job.cancel("borrowed projection cancelled")
        with pytest.raises(asyncio.CancelledError, match="borrowed projection cancelled"):
            await job
    finally:
        if not job.done():
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
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
            check_output_custom,
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
                _supported=(
                    *hamilton_compat._SUPPORTED,
                    resolve_from_config,
                    check_output_custom,
                ),
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


def test_public_driver_preserves_config_predicate_failure_without_hamilton_log(
    module_factory, monkeypatch, caplog
):
    calls = []
    callback_logger = logging.getLogger("sdax_hamilton_test.config_predicate")

    class Sentinel(RuntimeError):
        pass

    def predicate(configuration):
        callback_logger.warning("predicate callback ran")
        error = Sentinel("private sentinel")
        calls.append(id(error))
        raise error

    module = module_factory(
        """
from hamilton.function_modifiers import config

@config(predicate)
def result(value: int) -> int:
    return value
""",
        predicate=predicate,
    )
    capture_refs = []
    capture_class = hamilton_compat._ProvenanceCapture

    class ObservedCapture(capture_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            capture_refs.append(weakref.ref(self))

    monkeypatch.setattr(hamilton_compat, "_ProvenanceCapture", ObservedCapture)

    def construct() -> None:
        with pytest.raises(Sentinel) as result:
            Driver(module, config={"enabled": True})
        assert id(result.value) == calls[0]
        assert result.value.__context__ is None
        assert result.value.__cause__ is None

    construct()
    gc.collect()
    assert len(calls) == 1
    assert [
        record.getMessage()
        for record in caplog.records
        if record.name == callback_logger.name
    ] == ["predicate callback ran"]
    assert not [
        record
        for record in caplog.records
        if record.name == "hamilton.function_modifiers.base"
    ]
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


@pytest.mark.asyncio
async def test_delayed_pipeline_retains_selected_helper_policy_and_shutdown_once(module_factory):
    events: list[tuple[str, int]] = []
    resolver_calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, pipe_output, resolve_from_config, step
from sdax_hamilton import Acquisition, execution, shutdown

@execution(timeout=1)
def add(value: int) -> int:
    events.append(("add", value))
    return value + 1

@shutdown(of=add)
def close_add(state: Acquisition[int]) -> None:
    events.append(("close", state.value))

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return pipe_output(step(add))

@resolve_from_config(decorate_with=decorate_with)
def result(value: int) -> int:
    return value
""",
        events=events,
        resolver_calls=resolver_calls,
    )
    specs = hamilton_compat.compile_modules(
        (module,),
        {settings.ENABLE_POWER_USER_MODE: True},
        _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, pipe_output),
    )

    generated = specs["result.with_add"]
    assert resolver_calls == ["resolve"]
    assert generated.origin.endswith(".add")
    assert generated.policy.timeout == 1
    assert generated.ownership_required
    assert generated.release is not None
    async with PreparedPlan(specs, ["result"]).open(inputs={"value": 4}) as result:
        assert result == {"result": 5}
        assert events == [("add", 4)]
    assert events == [("add", 4), ("close", 5)]
    assert resolver_calls == ["resolve"]


@pytest.mark.asyncio
async def test_delayed_pipeline_discovers_external_helper_shutdown_before_effects(
    module_factory, caplog
):
    events: list[str] = []
    resolver_calls: list[str] = []
    component = module_factory(
        """
from sdax_hamilton import Acquisition, execution, shutdown

@execution(timeout=1)
def helper(value: int) -> int:
    events.append("helper")
    return value + 1

@shutdown(of=helper)
def close_helper(state: Acquisition[int]) -> None:
    events.append("close")
""",
        events=events,
    )
    root = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, pipe_output, resolve_from_config, step

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return pipe_output(step(helper))

@resolve_from_config(decorate_with=decorate_with)
def result(value: int) -> int:
    return value
""",
        helper=component.helper,
        resolver_calls=resolver_calls,
    )

    specs = hamilton_compat.compile_modules(
        (root,),
        {settings.ENABLE_POWER_USER_MODE: True},
        _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, pipe_output),
    )

    generated = specs["result.with_helper"]
    assert resolver_calls == ["resolve"]
    assert generated.policy.timeout == 1
    assert generated.ownership_required
    assert generated.release is not None
    assert events == []
    async with PreparedPlan(specs, ["result"]).open(inputs={"value": 4}) as result:
        assert result == {"result": 5}
    assert events == ["helper", "close"]
    assert not [
        record
        for record in caplog.records
        if record.name == "hamilton.function_modifiers.base"
    ]


def test_static_pipeline_rejects_callable_instance_before_effects(module_factory):
    events: list[int] = []
    module = module_factory(
        """
from hamilton.function_modifiers import pipe_output, step
from sdax_hamilton import execution

class Helper:
    __name__ = "helper"
    __globals__ = globals()
    __annotations__ = {"value": int, "return": int}

    def __call__(self, value: int) -> int:
        events.append(value)
        return value + 1

helper = execution(timeout=7)(Helper())

@pipe_output(step(helper))
def result(value: int) -> int:
    return value
""",
        events=events,
    )

    with pytest.raises(ValueError, match="pipeline steps require plain functions"):
        hamilton_compat.compile_modules(
            (module,),
            {},
            _supported=(*hamilton_compat._SUPPORTED, pipe_output),
        )

    assert events == []


def test_delayed_pipeline_rejects_callable_instance_after_one_resolver_call(module_factory):
    events: list[int] = []
    resolver_calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, pipe_output, resolve_from_config, step
from sdax_hamilton import execution

class Helper:
    __name__ = "helper"
    __globals__ = globals()
    __annotations__ = {"value": int, "return": int}

    def __call__(self, value: int) -> int:
        events.append(value)
        return value + 1

helper = execution(timeout=7)(Helper())

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return pipe_output(step(helper))

@resolve_from_config(decorate_with=decorate_with)
def result(value: int) -> int:
    return value
""",
        events=events,
        resolver_calls=resolver_calls,
    )

    with pytest.raises(ValueError, match="pipeline steps require plain functions"):
        hamilton_compat.compile_modules(
            (module,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, pipe_output),
        )

    assert resolver_calls == ["resolve"]
    assert events == []


def test_delayed_does_rejects_callable_instance_after_one_resolver_call(module_factory):
    events: list[int] = []
    resolver_calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import does, hamilton_exclude, resolve_from_config

class Replacement:
    __name__ = "replacement"
    __annotations__ = {"value": int, "return": int}

    def __call__(self, value: int) -> int:
        events.append(value)
        return value + 1

replacement = Replacement()

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return does(replacement)

@resolve_from_config(decorate_with=decorate_with)
def result(value: int) -> int:
    pass
""",
        events=events,
        resolver_calls=resolver_calls,
    )

    with pytest.raises(ValueError, match="does replacements require plain functions"):
        hamilton_compat.compile_modules(
            (module,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, does),
        )

    assert resolver_calls == ["resolve"]
    assert events == []


def test_delayed_subdag_rejects_hidden_unsupported_modifier_before_expansion(
    module_factory, monkeypatch
):
    from hamilton.function_modifiers.expanders import extract_fields
    from hamilton.function_modifiers.recursive import subdag

    resolver_calls: list[str] = []
    expansions: list[str] = []
    original_expand = extract_fields.transform_node

    def counted_expand(self, *args, **kwargs):
        expansions.append("extract")
        return original_expand(self, *args, **kwargs)

    monkeypatch.setattr(extract_fields, "transform_node", counted_expand)
    nested = module_factory(
        """
from hamilton.function_modifiers import extract_fields

class UnknownExtraction(extract_fields):
    pass

@UnknownExtraction({"number": int})
def hidden() -> dict[str, int]:
    return {"number": 1}
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, subdag

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return subdag(hidden)

@resolve_from_config(decorate_with=decorate_with)
def result(hidden: dict[str, int]) -> dict[str, int]:
    return hidden
""",
        hidden=nested.hidden,
        resolver_calls=resolver_calls,
    )

    with pytest.raises(ValueError, match="hidden: unsupported Hamilton decorator UnknownExtraction"):
        hamilton_compat.compile_modules(
            (root,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, subdag),
        )

    assert resolver_calls == ["resolve"]
    assert expansions == []


@pytest.mark.asyncio
async def test_subdag_keeps_exact_excluded_helper_untyped_and_ignores_it(module_factory):
    from hamilton.function_modifiers.recursive import subdag

    nested = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude

@hamilton_exclude
def ignored(value):
    raise AssertionError("excluded helper must not execute")

def selected() -> int:
    return 3
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(nested)
def result(selected: int) -> int:
    return selected
""",
        nested=nested,
    )

    specs = hamilton_compat.compile_modules(
        (root,),
        {},
        _supported=(*hamilton_compat._SUPPORTED, subdag),
    )

    assert await PreparedPlan(specs, ["result"]).execute() == {"result": 3}


def test_delayed_subdag_preflights_hidden_function_signature(module_factory):
    from hamilton.function_modifiers.recursive import subdag

    resolver_calls: list[str] = []
    nested = module_factory(
        """
def hidden(*values: int) -> int:
    return len(values)
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, subdag

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return subdag(hidden)

@resolve_from_config(decorate_with=decorate_with)
def result(hidden: int) -> int:
    return hidden
""",
        hidden=nested.hidden,
        resolver_calls=resolver_calls,
    )

    with pytest.raises(TypeError, match="hidden: variadic and positional-only parameters unsupported"):
        hamilton_compat.compile_modules(
            (root,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, subdag),
        )

    assert resolver_calls == ["resolve"]


def test_delayed_subdag_rejects_reflection_cycle_once(module_factory):
    from hamilton.function_modifiers.recursive import subdag

    resolver_calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, subdag

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return subdag(result)

@resolve_from_config(decorate_with=decorate_with)
def result(result: int) -> int:
    return result
""",
        resolver_calls=resolver_calls,
    )

    with pytest.raises(ValueError, match="Recursive subdag declaration cycle at result"):
        hamilton_compat.compile_modules(
            (module,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, subdag),
        )

    assert resolver_calls == ["resolve"]


def test_nested_delayed_subdag_rejects_reflection_cycle_once(module_factory):
    from hamilton.function_modifiers.recursive import subdag

    resolver_calls: list[str] = []
    nested = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, subdag

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return subdag(hidden)

@resolve_from_config(decorate_with=decorate_with)
def hidden(hidden: int) -> int:
    return hidden
""",
        resolver_calls=resolver_calls,
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(hidden)
def result(hidden: int) -> int:
    return hidden
""",
        hidden=nested.hidden,
    )

    with pytest.raises(ValueError, match="Recursive subdag declaration cycle at hidden"):
        hamilton_compat.compile_modules(
            (root,),
            {settings.ENABLE_POWER_USER_MODE: True},
            _supported=(*hamilton_compat._SUPPORTED, resolve_from_config, subdag),
        )

    assert resolver_calls == ["resolve"]


@pytest.mark.asyncio
async def test_subdag_source_collection_allows_acyclic_sibling_reuse(module_factory):
    from hamilton.function_modifiers.recursive import subdag

    nested = module_factory(
        """
from hamilton.function_modifiers import subdag

def second() -> int:
    return 2

@subdag(second)
def first(second: int) -> int:
    return second + 1
"""
    )
    root = module_factory(
        """
from hamilton.function_modifiers import subdag

@subdag(first, second)
def result(first: int, second: int) -> int:
    return first + second
""",
        first=nested.first,
        second=nested.second,
    )

    specs = hamilton_compat.compile_modules(
        (root,),
        {},
        _supported=(*hamilton_compat._SUPPORTED, subdag),
    )

    assert await PreparedPlan(specs, ["result"]).execute() == {"result": 5}
