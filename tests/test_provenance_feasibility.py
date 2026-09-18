"""Feasibility proof for provenance capture through Hamilton's real compiler path.

This is deliberately a test-local probe.  It establishes the interception seam
needed by the later NodeSpec work without admitting the decorators exercised here.
"""

import inspect
from collections import Counter
from collections.abc import Callable, Mapping
from copy import copy
from dataclasses import dataclass
from enum import Enum
from types import FunctionType, MethodType
from typing import Any, get_type_hints

import pytest
from hamilton import driver as hamilton_driver
from hamilton import node, settings
from hamilton.data_quality import base as data_quality
from hamilton.function_modifiers import base, parameterized_subdag
from hamilton.function_modifiers.expanders import extract_fields
from hamilton.function_modifiers.recursive import subdag
from hamilton.function_modifiers.validation import (
    BaseDataValidationDecorator,
    check_output_custom,
)

from sdax_hamilton import Acquisition, Driver, shutdown
from sdax_hamilton._model import MISSING, InputSpec, NodeSpec
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


class Role(Enum):
    ACQUISITION = "acquisition"
    PROJECTION_SOURCE = "projection-source"
    PROJECTION = "projection"
    VALIDATION_RAW = "validation-raw"
    VALIDATOR = "validator"
    VALIDATION_GATE = "validation-gate"
    ORDINARY = "ordinary"


@dataclass(frozen=True)
class Mount:
    declaration: Callable[..., Any]
    path: tuple[str, ...]


@dataclass(frozen=True)
class Provenance:
    role: Role
    declaration: Callable[..., Any]
    mount: Mount


@dataclass(frozen=True)
class Resolution:
    mount: Mount
    resolver: object
    resolved_type: type


class _ProjectionProbe(base.NodeTransformer):
    """Delegate one extraction transform and label its returned objects directly."""

    def __init__(
        self,
        inner: extract_fields,
        capture: "CaptureCompiler",
        declaration: Callable[..., Any],
    ) -> None:
        super().__init__(inner.target)
        self.inner = inner
        self.capture = capture
        self.declaration = declaration

    def transform_node(
        self, node_: node.Node, config: dict[str, Any], fn: Callable[..., Any]
    ) -> list[node.Node]:
        generated = list(self.inner.transform_node(node_, config, fn))
        self.capture.note(generated[0], Role.PROJECTION_SOURCE, self.declaration)
        for projection in generated[1:]:
            self.capture.note(projection, Role.PROJECTION, self.declaration)
        return generated

    def validate(self, fn: Callable[..., Any]) -> None:
        self.inner.validate(fn)

    def required_config(self) -> list[str] | None:
        return self.inner.required_config()

    def optional_config(self) -> dict[str, Any] | None:
        return self.inner.optional_config()


class _ValidationProbe(base.NodeTransformer):
    """Delegate one validation transform and label its returned objects directly."""

    def __init__(
        self,
        inner: BaseDataValidationDecorator,
        capture: "CaptureCompiler",
        declaration: Callable[..., Any],
    ) -> None:
        super().__init__(inner.target)
        self.inner = inner
        self.capture = capture
        self.declaration = declaration

    def transform_node(
        self, node_: node.Node, config: dict[str, Any], fn: Callable[..., Any]
    ) -> list[node.Node]:
        generated = list(self.inner.transform_node(node_, config, fn))
        for validator in generated[:-2]:
            self.capture.note(validator, Role.VALIDATOR, self.declaration)
        self.capture.note(generated[-2], Role.VALIDATION_GATE, self.declaration)
        self.capture.note(generated[-1], Role.VALIDATION_RAW, self.declaration)
        return generated

    def validate(self, fn: Callable[..., Any]) -> None:
        self.inner.validate(fn)

    def required_config(self) -> list[str] | None:
        return self.inner.required_config()

    def optional_config(self) -> dict[str, Any] | None:
        return self.inner.optional_config()


class _DelayedProbe(base.DynamicResolver):
    """Call one copied resolver once and wrap only the modifier it returned."""

    def __init__(
        self,
        inner: base.DynamicResolver,
        capture: "CaptureCompiler",
        declaration: Callable[..., Any],
    ) -> None:
        self.inner = inner
        self.capture = capture
        self.declaration = declaration

    def resolve(
        self, config: dict[str, Any], fn: Callable[..., Any]
    ) -> base.NodeTransformLifecycle:
        resolved = self.inner.resolve(config, fn)
        mount = self.capture.current_mount()
        self.capture.resolutions.append(Resolution(mount, self.inner, type(resolved)))
        if isinstance(resolved, BaseDataValidationDecorator):
            return _ValidationProbe(resolved, self.capture, self.declaration)
        raise AssertionError(f"Feasibility fixture returned {type(resolved)!r}")

    def validate(self, fn: Callable[..., Any]) -> None:
        self.inner.validate(fn)

    def required_config(self) -> list[str] | None:
        return self.inner.required_config()

    def optional_config(self) -> dict[str, Any] | None:
        return self.inner.optional_config()


class CaptureCompiler:
    """A bounded, disposable probe over copied declaration/modifier instances."""

    _LIFECYCLES = (
        base.NodeResolver,
        base.NodeCreator,
        base.NodeExpander,
        base.NodeTransformer,
        base.NodeInjector,
        base.NodeDecorator,
        base.DynamicResolver,
    )

    def __init__(self, releases: Mapping[Callable[..., Any], Callable[..., Any]]) -> None:
        self.releases = dict(releases)
        self._clones: dict[Callable[..., Any], Callable[..., Any]] = {}
        self._originals: dict[Callable[..., Any], Callable[..., Any]] = {}
        self._mounts: list[Mount] = []
        self._pending: dict[int, Provenance] = {}
        self.provenance: dict[str, Provenance] = {}
        self.resolutions: list[Resolution] = []

    def current_mount(self) -> Mount:
        if not self._mounts:
            raise AssertionError("Provenance event occurred outside a mounted subdag")
        return self._mounts[-1]

    def note(
        self, generated: node.Node, role: Role, declaration: Callable[..., Any]
    ) -> None:
        self._pending[id(generated.callable)] = Provenance(
            role,
            declaration,
            self.current_mount(),
        )

    def _modifier(
        self, modifier: base.NodeTransformLifecycle, declaration: Callable[..., Any]
    ) -> base.NodeTransformLifecycle:
        snapshot = copy(modifier)
        if isinstance(snapshot, parameterized_subdag):
            snapshot.load_from = tuple(self.clone(fn) for fn in snapshot.load_from)
            self._instrument_mounts(snapshot, declaration)
            return snapshot
        if isinstance(snapshot, extract_fields):
            return _ProjectionProbe(snapshot, self, declaration)
        if isinstance(snapshot, base.DynamicResolver):
            return _DelayedProbe(snapshot, self, declaration)
        return snapshot

    def clone(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        if fn in self._clones:
            return self._clones[fn]
        clone = FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
        self._clones[fn] = clone
        self._originals[clone] = fn
        clone.__kwdefaults__ = dict(fn.__kwdefaults__ or {})
        clone.__annotations__ = dict(fn.__annotations__)
        clone.__dict__.update(fn.__dict__)
        for stage in self._LIFECYCLES:
            key = stage.get_lifecycle_name()
            if hasattr(fn, key):
                setattr(clone, key, [self._modifier(item, fn) for item in getattr(fn, key)])
        clone.__module__ = fn.__module__
        clone.__qualname__ = fn.__qualname__
        clone.__doc__ = fn.__doc__
        return clone

    def _classify_collected(self, entry: node.Node) -> Provenance:
        recorded = self._pending.get(id(entry.callable))
        if recorded is not None:
            return recorded
        for origin in entry.originating_functions or ():
            declaration = self._originals.get(origin)
            if declaration in self.releases:
                return Provenance(Role.ACQUISITION, declaration, self.current_mount())
            if declaration is not None:
                return Provenance(Role.ORDINARY, declaration, self.current_mount())
        raise AssertionError(f"Unattributed generated node {entry!r}")

    def _instrument_mounts(
        self, modifier: parameterized_subdag, declaration: Callable[..., Any]
    ) -> None:
        gather = modifier._gather_subdag_generators

        def gather_with_capture(instance: parameterized_subdag) -> list[subdag]:
            generators = gather()
            for generator in generators:
                mount = Mount(declaration, (generator.namespace,))
                add_namespace = generator.add_namespace
                generate = generator.generate_nodes

                def add_namespace_with_capture(
                    nodes: list[node.Node],
                    namespace: str,
                    inputs: dict[str, Any] | None = None,
                    config: dict[str, Any] | None = None,
                    *,
                    _add_namespace=add_namespace,
                ) -> list[node.Node]:
                    generated = list(_add_namespace(nodes, namespace, inputs, config))
                    if len(generated) != len(nodes):
                        raise AssertionError("Subdag namespace operation changed node count")
                    for before, after in zip(nodes, generated, strict=True):
                        self.provenance[after.name] = self._classify_collected(before)
                    return generated

                def generate_with_capture(
                    fn: Callable[..., Any],
                    configuration: dict[str, Any],
                    *,
                    _generate=generate,
                    _mount=mount,
                ) -> list[node.Node]:
                    self._mounts.append(_mount)
                    try:
                        return list(_generate(fn, configuration))
                    finally:
                        self._mounts.pop()

                generator.add_namespace = add_namespace_with_capture
                generator.generate_nodes = generate_with_capture
            return generators

        modifier._gather_subdag_generators = MethodType(gather_with_capture, modifier)

    def resolve(
        self, fn: Callable[..., Any], configuration: Mapping[str, Any]
    ) -> tuple[node.Node, ...]:
        return tuple(base.resolve_nodes(self.clone(fn), dict(configuration)))

    def lower(self, resolved: tuple[node.Node, ...]) -> Mapping[str, NodeSpec]:
        specs = {}
        for entry in resolved:
            inputs = {}
            for name, (typ, dependency_type) in entry.input_types.items():
                default = entry.default_parameter_values.get(name, MISSING)
                if dependency_type is node.DependencyType.REQUIRED:
                    default = MISSING
                inputs[name] = InputSpec(typ, default)
            provenance = self.provenance.get(entry.name)
            release = None
            if provenance is not None and provenance.role is Role.ACQUISITION:
                release = self.releases[provenance.declaration]
            origin = ""
            if provenance is not None:
                origin = f"{provenance.declaration.__module__}.{provenance.declaration.__qualname__}"
            specs[entry.name] = NodeSpec(
                name=entry.name,
                fn=entry.callable,
                output_type=entry.type,
                inputs=inputs,
                release=release,
                origin=origin,
                ownership_required=release is not None,
            )
        return specs


def _make_fixture(module_factory, minimum: int):
    events: list[tuple[str, int]] = []
    resolver_calls: list[int] = []

    def make_check(configured_minimum: int):
        from hamilton.function_modifiers import check_output_custom

        resolver_calls.append(configured_minimum)
        return check_output_custom(MinimumValidator(configured_minimum))

    component = module_factory(
        """
from hamilton.function_modifiers import extract_fields, resolve_from_config
from sdax_hamilton import Acquisition, shutdown

def acquire(token: int) -> Handle:
    events.append(("acquire", token))
    return Handle(token, events)

@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    handle = state.value
    assert handle.live
    handle.live = False
    events.append(("release", handle.number))

@extract_fields({"number": int})
def projected(acquire: Handle) -> dict[str, int]:
    assert acquire.live
    return {"number": acquire.number}

@resolve_from_config(decorate_with=make_check)
def checked(number: int) -> int:
    return number
""",
        Acquisition=Acquisition,
        Handle=Handle,
        events=events,
        make_check=make_check,
        shutdown=shutdown,
    )
    mounted = module_factory(
        """
from hamilton.function_modifiers import parameterized_subdag, value

@parameterized_subdag(
    acquire,
    projected,
    checked,
    low={"inputs": {"token": value(2)}},
    high={"inputs": {"token": value(5)}},
)
def result(checked: int) -> int:
    return checked
""",
        acquire=component.acquire,
        checked=component.checked,
        projected=component.projected,
    )
    configuration = {
        settings.ENABLE_POWER_USER_MODE: True,
        "configured_minimum": minimum,
    }
    return component, mounted, configuration, events, resolver_calls


def _graph_signature(nodes: tuple[node.Node, ...]) -> dict[str, tuple[Any, dict[str, Any]]]:
    return {
        entry.name: (
            entry.type,
            {name: typ for name, (typ, _) in entry.input_types.items()},
        )
        for entry in nodes
    }


def _owner_dependencies(
    nodes: tuple[node.Node, ...], provenance: Mapping[str, Provenance], selected: str
) -> frozenset[str]:
    by_name = {entry.name: entry for entry in nodes}
    owners = set()
    stack = [selected]
    visited = set()
    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)
        fact = provenance.get(name)
        if fact is not None and fact.role is Role.ACQUISITION:
            owners.add(name)
        stack.extend(dependency for dependency in by_name[name].input_types if dependency in by_name)
    return frozenset(owners)


def _decorator_objects(fn: Callable[..., Any]) -> tuple[object, ...]:
    return tuple(
        modifier
        for stage in CaptureCompiler._LIFECYCLES
        for modifier in getattr(fn, stage.get_lifecycle_name(), ())
    )


def _leaves(error: BaseException) -> list[BaseException]:
    if isinstance(error, BaseExceptionGroup):
        return [leaf for child in error.exceptions for leaf in _leaves(child)]
    return [error]


@pytest.mark.asyncio
async def test_compositional_provenance_capture_without_compiler_replay(module_factory):
    stable = Driver(module_factory("def stable(value: int) -> int:\n    return value + 1")).prepare(
        ["stable"]
    )
    component, mounted, configuration, events, resolver_calls = _make_fixture(module_factory, 1)
    originals = {
        fn: _decorator_objects(fn)
        for fn in (component.acquire, component.projected, component.checked, mounted.result)
    }
    resolve_nodes = base.resolve_nodes

    compiler = CaptureCompiler({component.acquire: component.close})
    captured_nodes = compiler.resolve(mounted.result, configuration)

    stock_component, stock_mounted, stock_config, _, stock_resolver_calls = _make_fixture(
        module_factory, 1
    )
    stock_nodes = tuple(base.resolve_nodes(stock_mounted.result, stock_config))
    assert _graph_signature(captured_nodes) == _graph_signature(stock_nodes)
    assert resolver_calls == [1, 1]
    assert stock_resolver_calls == [1, 1]

    counts = Counter(resolution.mount.path for resolution in compiler.resolutions)
    assert counts == Counter({("low",): 1, ("high",): 1})
    assert all(resolution.resolved_type is check_output_custom for resolution in compiler.resolutions)
    assert all(resolution.mount.declaration is mounted.result for resolution in compiler.resolutions)
    original_resolver = originals[component.checked][0]
    assert all(
        resolution.resolver is not original_resolver
        and type(resolution.resolver) is type(original_resolver)
        for resolution in compiler.resolutions
    )

    expected_roles = {
        "acquire": Role.ACQUISITION,
        "projected": Role.PROJECTION_SOURCE,
        "number": Role.PROJECTION,
        "checked_raw": Role.VALIDATION_RAW,
        "checked_minimum": Role.VALIDATOR,
        "checked": Role.VALIDATION_GATE,
    }
    for mount in ("low", "high"):
        assert {
            name: compiler.provenance[f"{mount}.{name}"].role for name in expected_roles
        } == expected_roles
    assert _owner_dependencies(captured_nodes, compiler.provenance, "low.checked") == frozenset(
        {"low.acquire"}
    )
    assert _owner_dependencies(captured_nodes, compiler.provenance, "high.checked") == frozenset(
        {"high.acquire"}
    )

    checked_roles = {
        name: entry.originating_functions
        for name, entry in {item.name: item for item in captured_nodes}.items()
        if name in {"low.checked_raw", "low.checked_minimum", "low.checked"}
    }
    assert len({origins for origins in checked_roles.values()}) == 1
    assert inspect.signature(component.checked).parameters["number"].annotation is int
    assert get_type_hints(component.acquire)["return"] is Handle

    plan = PreparedPlan(compiler.lower(captured_nodes), ["low", "high"])
    assert await plan.execute() == {"low": 2, "high": 5}
    assert resolver_calls == [1, 1]
    assert Counter(events) == Counter(
        {("acquire", 2): 1, ("release", 2): 1, ("acquire", 5): 1, ("release", 5): 1}
    )

    oracle_component, oracle_mounted, oracle_config, _, oracle_resolver_calls = _make_fixture(
        module_factory, 1
    )
    oracle = (
        hamilton_driver.Builder()
        .with_modules(oracle_mounted)
        .with_config(oracle_config)
        .build()
    )
    assert oracle.execute(["low", "high"]) == {"low": 2, "high": 5}
    assert oracle_resolver_calls == [1, 1]
    assert oracle_component.acquire is not component.acquire

    assert base.resolve_nodes is resolve_nodes
    for fn, decorators in originals.items():
        assert _decorator_objects(fn) == decorators
    assert "_gather_subdag_generators" not in originals[mounted.result][0].__dict__
    assert await stable.execute(inputs={"value": 6}) == {"stable": 7}


@pytest.mark.asyncio
async def test_validation_failure_retains_each_actual_mount_owner_once(module_factory):
    component, mounted, configuration, events, resolver_calls = _make_fixture(module_factory, 4)
    compiler = CaptureCompiler({component.acquire: component.close})
    captured_nodes = compiler.resolve(mounted.result, configuration)
    plan = PreparedPlan(compiler.lower(captured_nodes), ["low", "high"])

    with pytest.raises(BaseExceptionGroup) as result:
        await plan.execute()

    assert any(isinstance(error, data_quality.DataValidationError) for error in _leaves(result.value))
    assert resolver_calls == [4, 4]
    assert Counter(resolution.mount.path for resolution in compiler.resolutions) == Counter(
        {("low",): 1, ("high",): 1}
    )
    assert Counter(events) == Counter(
        {("acquire", 2): 1, ("release", 2): 1, ("acquire", 5): 1, ("release", 5): 1}
    )
