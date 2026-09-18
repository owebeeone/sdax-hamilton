"""Construction-local capture for Hamilton modifier provenance.

The cohesion review keeps copying, interception and identity handoff together
because they share construction-only identity tables. Revisit this boundary when
those responsibilities can separate without duplicating state.
"""

from collections.abc import Callable, Collection, Mapping
from copy import copy
from dataclasses import dataclass, field, replace
from types import FunctionType, MappingProxyType, MethodType
from typing import Any

from hamilton import node
from hamilton.function_modifiers import base, parameterize, parameterized_subdag
from hamilton.function_modifiers.adapters import LoadFromDecorator
from hamilton.function_modifiers.delayed import resolve, resolve_from_config
from hamilton.function_modifiers.expanders import extract_fields
from hamilton.function_modifiers.macros import (
    does,
    dynamic_transform,
    model,
    pipe,
    pipe_input,
    pipe_output,
)
from hamilton.function_modifiers.recursive import subdag, with_columns_base
from hamilton.function_modifiers.validation import (
    BaseDataValidationDecorator,
    check_output,
    check_output_custom,
)

from ._construction import wrap_lifecycle
from ._hamilton_loader import install_load_from_correction
from ._hamilton_pipeline import (
    correct_copied_async_output_pipeline,
    correct_copied_async_output_pipelines,
    selected_step_input_contracts,
    snapshot_copied_macro_bindings,
    snapshot_copied_macro_modifier,
    validate_copied_macro_bindings,
    validate_copied_macro_modifier,
)
from ._hamilton_validation import (
    correct_validation_gate,
    correct_validation_representation,
)
from ._model import GeneratedRole, InputSpec
from ._optional_profiles import identify_optional_modifier, validate_optional_profile

_LIFECYCLES = (
    base.NodeResolver,
    base.NodeCreator,
    base.NodeExpander,
    base.NodeTransformer,
    base.NodeInjector,
    base.NodeDecorator,
    base.DynamicResolver,
)
@dataclass(frozen=True)
class _CapturedFact:
    role: GeneratedRole
    declaration: Callable[..., Any]
    actual_call: bool
    borrows: bool
    public_name: str
    mount: object
    input_contracts: Mapping[str, InputSpec] = field(
        default_factory=lambda: MappingProxyType({})
    )


class _ProvenanceCapture:
    """Construction-local facts captured from copied Hamilton modifiers."""

    def __init__(
        self,
        owned: Collection[Callable[..., Any]],
        supported: Collection[type[base.NodeTransformLifecycle]],
    ) -> None:
        self.owned = frozenset(owned)
        self.supported = frozenset(supported)
        self._clones: dict[Callable[..., Any], Callable[..., Any]] = {}
        self._helper_clones: dict[FunctionType, FunctionType] = {}
        self._originals: dict[Callable[..., Any], Callable[..., Any]] = {}
        self._root_mount = object()
        self._mounts: list[tuple[object, tuple[str, ...]]] = []
        self._pending: dict[
            tuple[object, int], tuple[Callable[..., Any], _CapturedFact]
        ] = {}
        self._installed_methods: list[tuple[object, str, bool, object | None]] = []

    def _mount(self) -> tuple[object, tuple[str, ...]]:
        return self._mounts[-1] if self._mounts else (self._root_mount, ())

    def _remember(
        self,
        entry: node.Node,
        role: GeneratedRole,
        declaration: Callable[..., Any],
        *,
        actual_call: bool,
        borrows: bool | None = None,
        public_name: str | None = None,
        input_contracts: Mapping[str, InputSpec] | None = None,
    ) -> None:
        mount, _ = self._mount()
        callable_ = entry.callable
        contracts = MappingProxyType(dict(input_contracts or {}))
        unknown = contracts.keys() - entry.input_types.keys()
        if unknown:
            raise AssertionError(
                f"Captured contracts are not inputs of {entry.name}: {sorted(unknown)}"
            )
        self._pending[(mount, id(callable_))] = (
            callable_,
            _CapturedFact(
                role=role,
                declaration=declaration,
                actual_call=actual_call,
                borrows=(
                    role
                    in (
                        GeneratedRole.PROJECTION,
                        GeneratedRole.VALIDATION_RAW,
                        GeneratedRole.VALIDATION_GATE,
                    )
                    if borrows is None
                    else borrows
                ),
                public_name=entry.name if public_name is None else public_name,
                mount=mount,
                input_contracts=contracts,
            ),
        )

    def _handoff(
        self,
        entry: node.Node,
        mount: object,
        fact: _CapturedFact,
        *,
        before: node.Node | None = None,
    ) -> None:
        contracts = fact.input_contracts
        if contracts:
            if before is None:
                raise AssertionError("Captured contract handoff requires its source node")
            before_inputs = tuple(before.input_types)
            after_inputs = tuple(entry.input_types)
            if len(before_inputs) != len(after_inputs):
                raise AssertionError("Subdag namespace operation changed captured inputs")
            # Hamilton 1.90 add_namespace preserves dependency order and contracts.
            # Distinct contracts detect reordering here; same-typed edges remain
            # guarded by the exact-version boundary and its pinned implementation.
            if tuple(before.input_types.values()) != tuple(entry.input_types.values()):
                raise AssertionError("Subdag namespace operation reordered captured inputs")
            renames = dict(zip(before_inputs, after_inputs, strict=True))
            contracts = MappingProxyType(
                {renames[name]: contract for name, contract in contracts.items()}
            )
            fact = replace(fact, input_contracts=contracts)
        callable_ = entry.callable
        self._pending[(mount, id(callable_))] = (callable_, fact)

    def _fact_from_callable(self, entry: node.Node) -> _CapturedFact | None:
        mount, _ = self._mount()
        recorded = self._pending.get((mount, id(entry.callable)))
        if recorded is None:
            return None
        callable_, fact = recorded
        if callable_ is not entry.callable:
            raise AssertionError("Captured callable identity was reused")
        return fact

    def _fact_before_namespace(self, entry: node.Node) -> _CapturedFact:
        recorded = self._fact_from_callable(entry)
        if recorded is not None:
            return recorded
        for origin in entry.originating_functions or ():
            declaration = self._originals.get(origin)
            if declaration is not None:
                mount, _ = self._mount()
                return _CapturedFact(
                    GeneratedRole.VALUE,
                    declaration,
                    True,
                    False,
                    entry.name,
                    mount,
                )
        raise AssertionError(f"Unattributed generated Hamilton node {entry.name}")

    def _install_method(self, instance: object, name: str, method: MethodType) -> None:
        state = vars(instance)
        self._installed_methods.append((instance, name, name in state, state.get(name)))
        setattr(instance, name, method)

    def _instrument_extract_fields(
        self, modifier: extract_fields, declaration: Callable[..., Any]
    ) -> None:
        transform = modifier.transform_node

        def transform_with_capture(
            instance: extract_fields,
            entry: node.Node,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> list[node.Node]:
            incoming = self._fact_from_callable(entry)
            if incoming is None:
                incoming = _CapturedFact(
                    GeneratedRole.VALUE,
                    declaration,
                    True,
                    False,
                    entry.name,
                    self._mount()[0],
                )
            generated = list(transform(entry, configuration, fn))
            self._remember(
                generated[0],
                incoming.role,
                incoming.declaration,
                actual_call=incoming.actual_call,
                borrows=incoming.borrows,
                public_name=incoming.public_name,
                input_contracts=incoming.input_contracts,
            )
            for projection in generated[1:]:
                self._remember(
                    projection,
                    GeneratedRole.PROJECTION,
                    incoming.declaration,
                    actual_call=False,
                )
            return generated

        self._install_method(
            modifier,
            "transform_node",
            MethodType(transform_with_capture, modifier),
        )

    def _instrument_validation(
        self,
        modifier: BaseDataValidationDecorator,
        declaration: Callable[..., Any],
        *,
        profile: str | None = None,
    ) -> None:
        transform = modifier.transform_node

        def transform_with_capture(
            instance: BaseDataValidationDecorator,
            entry: node.Node,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> list[node.Node]:
            incoming = self._fact_from_callable(entry)
            actual_call = True if incoming is None else incoming.actual_call
            public_name = entry.name if incoming is None else incoming.public_name
            captured_declaration = declaration if incoming is None else incoming.declaration
            generated = list(
                correct_validation_representation(
                    correct_validation_gate(transform(entry, configuration, fn)),
                    profile,
                )
            )
            for evidence in generated[:-2]:
                self._remember(
                    evidence,
                    GeneratedRole.VALIDATION_EVIDENCE,
                    captured_declaration,
                    actual_call=False,
                )
            self._remember(
                generated[-2],
                GeneratedRole.VALIDATION_GATE,
                captured_declaration,
                actual_call=False,
                public_name=public_name,
            )
            self._remember(
                generated[-1],
                GeneratedRole.VALIDATION_RAW,
                captured_declaration,
                actual_call=actual_call,
                public_name=public_name,
                input_contracts=(
                    MappingProxyType({}) if incoming is None else incoming.input_contracts
                ),
            )
            return generated

        self._install_method(
            modifier,
            "transform_node",
            MethodType(transform_with_capture, modifier),
        )

    def _selected_pipeline_steps(
        self,
        modifier: pipe_input | pipe_output,
        declaration: Callable[..., Any],
    ) -> list[tuple[Callable[..., Any], bool, Mapping[str, InputSpec]]]:
        selected: list[tuple[Callable[..., Any], bool, Mapping[str, InputSpec]]] = []

        def instrument(applicable: Any, fact: tuple[Callable[..., Any], bool]) -> None:
            bind = applicable.bind_function_args
            namespaced = applicable.namespaced

            def bind_with_capture(
                instance: Any,
                current_parameter: str | None,
                *,
                _bind=bind,
                _fact=fact,
            ):
                upstream_inputs, literal_inputs = _bind(current_parameter)
                selected.append(
                    (*_fact, selected_step_input_contracts(instance, upstream_inputs))
                )
                return upstream_inputs, literal_inputs

            def namespaced_with_capture(
                instance: Any,
                namespace: Any,
                *,
                _namespaced=namespaced,
                _fact=fact,
            ):
                derived = _namespaced(namespace)
                instrument(derived, _fact)
                return derived

            self._install_method(
                applicable,
                "bind_function_args",
                MethodType(bind_with_capture, applicable),
            )
            self._install_method(
                applicable,
                "namespaced",
                MethodType(namespaced_with_capture, applicable),
            )

        for applicable in modifier.transforms:
            helper = self._originals.get(applicable.fn)
            fact = (declaration, False) if helper is None else (helper, True)
            instrument(applicable, fact)
        return selected

    def _instrument_does(
        self, modifier: does, declaration: Callable[..., Any]
    ) -> None:
        generate = modifier.generate_nodes

        def generate_with_capture(
            instance: does,
            fn: Callable[..., Any],
            configuration: dict[str, Any],
        ) -> list[node.Node]:
            generated = list(generate(fn, configuration))
            if len(generated) != 1:
                raise AssertionError("Hamilton does expansion changed shape")
            self._remember(
                generated[0],
                GeneratedRole.VALUE,
                declaration,
                actual_call=True,
                public_name=generated[0].name,
            )
            return generated

        self._install_method(
            modifier,
            "generate_nodes",
            MethodType(generate_with_capture, modifier),
        )

    def _instrument_pipe_input(
        self, modifier: pipe_input, declaration: Callable[..., Any]
    ) -> None:
        inject_nodes = modifier.inject_nodes
        selected = self._selected_pipeline_steps(modifier, declaration)

        def inject_with_capture(
            instance: pipe_input,
            params: dict[str, type[type]],
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> tuple[list[node.Node], dict[str, str]]:
            selected_start = len(selected)
            generated, renames = inject_nodes(params, configuration, fn)
            generated = list(generated)
            step_facts = selected[selected_start:]
            if len(generated) != len(step_facts):
                raise AssertionError("Hamilton pipe_input selection changed shape")
            for step_node, (step_declaration, actual_call, input_contracts) in zip(
                generated, step_facts, strict=True
            ):
                if input_contracts and set(input_contracts) != set(step_node.input_types):
                    raise AssertionError("Hamilton pipeline input names changed during expansion")
                self._remember(
                    step_node,
                    GeneratedRole.VALUE,
                    step_declaration,
                    actual_call=actual_call,
                    borrows=not actual_call,
                    public_name=step_node.name,
                    input_contracts=input_contracts,
                )
            return generated, renames

        self._install_method(
            modifier,
            "inject_nodes",
            MethodType(inject_with_capture, modifier),
        )

    def _instrument_pipe_output(
        self, modifier: pipe_output, declaration: Callable[..., Any]
    ) -> None:
        transform = modifier.transform_node
        selected = self._selected_pipeline_steps(modifier, declaration)

        def transform_with_capture(
            instance: pipe_output,
            entry: node.Node,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> list[node.Node]:
            incoming = self._fact_from_callable(entry)
            selected_start = len(selected)
            generated = list(transform(entry, configuration, fn))
            if len(generated) == 1 and generated[0] is entry:
                return generated
            if len(generated) < 3:
                raise AssertionError("Hamilton pipe_output expansion changed shape")
            if incoming is None:
                incoming = _CapturedFact(
                    GeneratedRole.VALUE,
                    declaration,
                    True,
                    False,
                    entry.name,
                    self._mount()[0],
                )
            self._remember(
                generated[0],
                GeneratedRole.VALUE,
                incoming.declaration,
                actual_call=incoming.actual_call,
                borrows=incoming.borrows,
                public_name=incoming.public_name,
                input_contracts=incoming.input_contracts,
            )
            step_facts = selected[selected_start:]
            if len(generated[1:-1]) != len(step_facts):
                raise AssertionError("Hamilton pipe_output selection changed shape")
            for step_node, (step_declaration, actual_call, input_contracts) in zip(
                generated[1:-1], step_facts, strict=True
            ):
                if input_contracts and set(input_contracts) != set(step_node.input_types):
                    raise AssertionError("Hamilton pipeline input names changed during expansion")
                self._remember(
                    step_node,
                    GeneratedRole.VALUE,
                    step_declaration,
                    actual_call=actual_call,
                    borrows=not actual_call,
                    public_name=step_node.name,
                    input_contracts=input_contracts,
                )
            self._remember(
                generated[-1],
                GeneratedRole.VALUE,
                incoming.declaration,
                actual_call=False,
                borrows=True,
                public_name=incoming.public_name,
            )
            return generated

        self._install_method(
            modifier,
            "transform_node",
            MethodType(transform_with_capture, modifier),
        )

    def _instrument_resolver(
        self, modifier: resolve, declaration: Callable[..., Any]
    ) -> None:
        resolve_modifier = modifier.resolve

        def resolve_with_capture(
            instance: resolve,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> base.NodeTransformLifecycle:
            resolved = copy(resolve_modifier(configuration, fn))
            if type(resolved) not in self.supported:
                raise ValueError(
                    f"{declaration.__name__}: resolver returned unsupported Hamilton decorator "
                    f"{type(resolved).__name__}"
                )
            snapshot_copied_macro_modifier(
                resolved,
                copy_function=self._copy_helper,
            )
            correct_copied_async_output_pipeline(fn, resolved)
            validate_copied_macro_modifier(fn, resolved)
            return self._instrument_modifier(resolved, declaration)

        self._install_method(modifier, "resolve", MethodType(resolve_with_capture, modifier))

    def _instrument_parameterized_subdag(
        self, modifier: parameterized_subdag, declaration: Callable[..., Any]
    ) -> None:
        nested = []
        for item in modifier.load_from:
            if not isinstance(item, FunctionType):
                raise ValueError(
                    f"{declaration.__name__}: feasibility subdag requires function declarations"
                )
            nested.append(self.clone(item))
        modifier.load_from = tuple(nested)
        modifier.inputs = {name: copy(binding) for name, binding in modifier.inputs.items()}
        modifier.config = dict(modifier.config)
        modifier.external_inputs = list(modifier.external_inputs)
        modifier.parameterization = {
            name: {
                key: (
                    {item: copy(value) for item, value in setting.items()}
                    if key in ("inputs", "config")
                    else list(setting)
                )
                for key, setting in parameters.items()
            }
            for name, parameters in modifier.parameterization.items()
        }
        gather = modifier._gather_subdag_generators

        def gather_with_capture(instance: parameterized_subdag) -> list[subdag]:
            generators = gather()
            parent_mount, parent_path = self._mount()
            for generator in generators:
                mount = object()
                path = (*parent_path, generator.namespace)
                add_namespace = generator.add_namespace
                generate = generator.generate_nodes

                def add_namespace_with_capture(
                    nodes: list[node.Node],
                    namespace: str,
                    inputs: dict[str, Any] | None = None,
                    config: dict[str, Any] | None = None,
                    *,
                    _add_namespace=add_namespace,
                    _mount=mount,
                ) -> list[node.Node]:
                    generated = list(_add_namespace(nodes, namespace, inputs, config))
                    if len(generated) != len(nodes):
                        raise AssertionError("Subdag namespace operation changed node count")
                    if self._mount()[0] is not _mount:
                        raise AssertionError("Subdag namespace operation escaped its mount")
                    for before, after in zip(nodes, generated, strict=True):
                        self._handoff(
                            after,
                            parent_mount,
                            self._fact_before_namespace(before),
                            before=before,
                        )
                    return generated

                def generate_with_capture(
                    fn: Callable[..., Any],
                    configuration: dict[str, Any],
                    *,
                    _generate=generate,
                    _mount=mount,
                    _path=path,
                ) -> list[node.Node]:
                    self._mounts.append((_mount, _path))
                    try:
                        return list(_generate(fn, configuration))
                    finally:
                        self._mounts.pop()

                self._install_method(
                    generator,
                    "add_namespace",
                    MethodType(
                        lambda _instance, *args, _call=add_namespace_with_capture, **kwargs: _call(
                            *args, **kwargs
                        ),
                        generator,
                    ),
                )
                self._install_method(
                    generator,
                    "generate_nodes",
                    MethodType(
                        lambda _instance, *args, _call=generate_with_capture, **kwargs: _call(
                            *args, **kwargs
                        ),
                        generator,
                    ),
                )
            return generators

        self._install_method(
            modifier,
            "_gather_subdag_generators",
            MethodType(gather_with_capture, modifier),
        )

    def _instrument_with_columns(
        self,
        modifier: with_columns_base,
        declaration: Callable[..., Any],
        profile: str,
    ) -> None:
        validate_optional_profile(profile)
        nested_originals: dict[FunctionType, FunctionType] = {}
        nested = []
        for original in modifier.subdag_functions:
            if type(original) is not FunctionType:
                raise ValueError("with_columns requires plain nested functions")
            if hasattr(original, "__sdax_shutdown__"):
                continue
            cloned = self.clone(original)
            if not isinstance(cloned, FunctionType):
                raise AssertionError("Copied with_columns declaration is not a function")
            nested.append(cloned)
            nested_originals[cloned] = original
        modifier.subdag_functions = nested
        for name in ("select", "initial_schema", "config_required"):
            value = getattr(modifier, name)
            if value is not None and type(value) is not list:
                raise ValueError(f"with_columns {name} must be a list or None")
            setattr(modifier, name, None if value is None else list(value))

        chain_subdag_nodes = modifier.chain_subdag_nodes
        inject_nodes = modifier.inject_nodes
        before_namespace: list[tuple[node.Node, _CapturedFact]] = []

        def fact_before_namespace(entry: node.Node) -> _CapturedFact:
            incoming = self._fact_from_callable(entry)
            if incoming is not None:
                return incoming
            origins = set()
            for origin in entry.originating_functions or ():
                if not isinstance(origin, FunctionType):
                    continue
                original = nested_originals.get(origin)
                if original is not None:
                    origins.add(original)
            if len(origins) > 1:
                raise AssertionError("with_columns node has multiple nested origins")
            mount, _ = self._mount()
            if origins:
                return _CapturedFact(
                    GeneratedRole.VALUE,
                    origins.pop(),
                    True,
                    False,
                    entry.name,
                    mount,
                )
            return _CapturedFact(
                GeneratedRole.VALUE,
                declaration,
                False,
                True,
                entry.name,
                mount,
            )

        def chain_with_capture(
            instance: with_columns_base,
            fn: Callable[..., Any],
            inject_parameter: str,
            generated_nodes: Collection[node.Node],
        ) -> tuple[list[node.Node], str]:
            generated, current = chain_subdag_nodes(fn, inject_parameter, generated_nodes)
            generated = list(generated)
            before_namespace[:] = [
                (entry, fact_before_namespace(entry)) for entry in generated
            ]
            return generated, current

        def inject_with_capture(
            instance: with_columns_base,
            params: dict[str, type[type]],
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> tuple[list[node.Node], dict[str, str]]:
            before_namespace.clear()
            generated, renames = inject_nodes(params, configuration, fn)
            generated = list(generated)
            if len(generated) != len(before_namespace):
                raise AssertionError("with_columns namespace operation changed node count")
            mount, _ = self._mount()
            for after, (before, fact) in zip(
                generated, before_namespace, strict=True
            ):
                self._handoff(after, mount, fact, before=before)
            return generated, renames

        self._install_method(
            modifier,
            "chain_subdag_nodes",
            MethodType(chain_with_capture, modifier),
        )
        self._install_method(
            modifier,
            "inject_nodes",
            MethodType(inject_with_capture, modifier),
        )

    def _instrument_modifier(
        self, snapshot: base.NodeTransformLifecycle, declaration: Callable[..., Any]
    ) -> base.NodeTransformLifecycle:
        optional_profile = identify_optional_modifier(snapshot)
        if (
            optional_profile in ("pandas", "polars")
            and isinstance(snapshot, with_columns_base)
        ):
            self._instrument_with_columns(snapshot, declaration, optional_profile)
        elif type(snapshot) is parameterized_subdag:
            self._instrument_parameterized_subdag(snapshot, declaration)
        elif type(snapshot) is extract_fields:
            self._instrument_extract_fields(snapshot, declaration)
        elif type(snapshot) in (resolve, resolve_from_config):
            self._instrument_resolver(snapshot, declaration)
        elif type(snapshot) in (check_output, check_output_custom):
            self._instrument_validation(snapshot, declaration)
        elif type(snapshot) is does:
            self._instrument_does(snapshot, declaration)
        elif type(snapshot) in (pipe_input, pipe):
            self._instrument_pipe_input(snapshot, declaration)
        elif type(snapshot) is pipe_output:
            self._instrument_pipe_output(snapshot, declaration)
        elif type(snapshot) is LoadFromDecorator:
            install_load_from_correction(snapshot)
        elif type(snapshot) in (model, dynamic_transform):
            self._install_method(
                snapshot,
                "required_config",
                MethodType(lambda instance: instance.require_config(), snapshot),
            )
        wrap_result = (
            wrap_lifecycle
            if snapshot.get_lifecycle_name() == "dynamic"
            and type(snapshot) not in (resolve, resolve_from_config)
            else None
        )
        return wrap_lifecycle(snapshot, wrap_result=wrap_result)

    def _copy_helper(self, fn: FunctionType) -> FunctionType:
        existing = self._helper_clones.get(fn)
        if existing is not None:
            return existing
        clone = _copy_function(fn)
        self._helper_clones[fn] = clone
        self._originals[clone] = fn
        return clone

    def clone(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        existing = self._clones.get(fn)
        if existing is not None:
            return existing
        clone = _copy_function(fn)
        self._clones[fn] = clone
        self._originals[clone] = fn
        snapshot_copied_macro_bindings(clone, copy_function=self._copy_helper)
        correct_copied_async_output_pipelines(clone)
        validate_copied_macro_bindings(clone)
        for stage in _LIFECYCLES:
            key = stage.get_lifecycle_name()
            if hasattr(clone, key):
                setattr(
                    clone,
                    key,
                    [self._instrument_modifier(item, fn) for item in getattr(clone, key)],
                )
        return clone

    def fact(self, entry: node.Node) -> _CapturedFact:
        recorded = self._fact_from_callable(entry)
        if recorded is not None:
            return recorded
        for origin in entry.originating_functions or ():
            declaration = self._originals.get(origin)
            if declaration is not None:
                mount, _ = self._mount()
                return _CapturedFact(
                    GeneratedRole.VALUE,
                    declaration,
                    True,
                    False,
                    entry.name,
                    mount,
                )
        raise AssertionError(f"Unattributed resolved Hamilton node {entry.name}")

    def borrow_from(
        self,
        resolved: Collection[node.Node],
        facts: Mapping[str, _CapturedFact],
    ) -> dict[str, frozenset[str]]:
        by_name = {entry.name: entry for entry in resolved}
        owners = {
            name
            for name, fact in facts.items()
            if fact.actual_call and fact.declaration in self.owned
        }
        borrowed = {}
        for name, fact in facts.items():
            if not fact.borrows:
                continue
            found = set()
            visited = set()
            stack = list(by_name[name].input_types)
            while stack:
                dependency = stack.pop()
                if dependency in visited or dependency not in by_name:
                    continue
                visited.add(dependency)
                if dependency in owners:
                    found.add(dependency)
                stack.extend(by_name[dependency].input_types)
            if found:
                borrowed[name] = frozenset(found)
        return borrowed

    def finalize(self) -> None:
        """Detach interception methods and drop construction-only identity tables."""
        for instance, name, had_value, value in reversed(self._installed_methods):
            if had_value:
                setattr(instance, name, value)
            else:
                vars(instance).pop(name, None)
        self._installed_methods.clear()
        self._pending.clear()
        self._clones.clear()
        self._helper_clones.clear()
        self._originals.clear()
        self._mounts.clear()


def _copy_function(fn: Callable[..., Any]) -> FunctionType:
    """Copy one function and its bounded modifier containers."""
    clone = FunctionType(
        fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__
    )
    clone.__kwdefaults__ = dict(fn.__kwdefaults__ or {})
    clone.__annotations__ = dict(fn.__annotations__)
    clone.__dict__.update(fn.__dict__)
    for stage in _LIFECYCLES:
        key = stage.get_lifecycle_name()
        if hasattr(fn, key):
            modifiers = []
            for modifier in getattr(fn, key):
                snapshot = copy(modifier)
                if isinstance(modifier, parameterize):
                    snapshot.parameterization = {
                        output: {name: copy(binding) for name, binding in bindings.items()}
                        for output, bindings in modifier.parameterization.items()
                    }
                modifiers.append(snapshot)
            setattr(clone, key, modifiers)
    clone.__module__ = fn.__module__
    clone.__qualname__ = fn.__qualname__
    clone.__doc__ = fn.__doc__
    return clone
