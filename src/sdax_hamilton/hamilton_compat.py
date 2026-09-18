"""Version-bounded translation of real Hamilton declarations into owned node specs.

Hamilton's internal APIs are deliberately confined here. No Hamilton executor or
mutable graph escapes this boundary; SDAX receives only our immutable node model.
"""

import inspect
from collections.abc import Callable, Collection, Mapping
from copy import copy
from importlib import metadata
from types import FunctionType, MappingProxyType, MethodType, ModuleType
from typing import Any, get_args, get_origin, get_type_hints

import hamilton
from hamilton import graph, node
from hamilton.function_modifiers import (
    base,
    config,
    hamilton_exclude,
    inject,
    parameterize,
    parameterize_sources,
    parameterize_values,
    parameterized_inputs,
    parameterized_subdag,
    parametrized,
    parametrized_input,
    tag,
    tag_outputs,
)
from hamilton.function_modifiers.delayed import resolve_from_config
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.function_modifiers.expanders import extract_fields
from hamilton.function_modifiers.metadata import RayRemote, SchemaOutput, cache
from hamilton.function_modifiers.recursive import subdag
from hamilton.function_modifiers.validation import (
    BaseDataValidationDecorator,
    check_output_custom,
)
from hamilton.graph_utils import find_functions
from hamilton.lifecycle.base import LifecycleAdapterSet

from ._construction import resolve_nodes as _resolve_nodes
from ._construction import wrap_lifecycle
from ._model import MISSING, GeneratedRole, InputSpec, NodeSpec
from ._types import accepts, compatible, validate_type
from .declarations import Acquisition, Policy

SUPPORTED_HAMILTON_VERSION = "1.90.0"
SUPPORTED_SDAX_VERSION = "0.7.2"
_LIFECYCLES = (
    base.NodeResolver,
    base.NodeCreator,
    base.NodeExpander,
    base.NodeTransformer,
    base.NodeInjector,
    base.NodeDecorator,
    base.DynamicResolver,
)
_EXCLUDED = type(hamilton_exclude)
_SUPPORTED = (
    config,
    inject,
    parameterize,
    parameterize_sources,
    parameterize_values,
    parametrized,
    parametrized_input,
    parameterized_inputs,
    tag,
    tag_outputs,
    SchemaOutput,
    cache,
    RayRemote,
)
_PARAMETERIZE_INTERNAL_INPUTS = frozenset(
    (
        "upstream_dependencies",
        "literal_dependencies",
        "grouped_list_dependencies",
        "grouped_dict_dependencies",
        "former_inputs",
    )
)


def _check_version():
    """Fail closed if a distribution or imported source differs from the tested API."""
    try:
        installed = metadata.version("apache-hamilton")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("sdax-hamilton requires apache-hamilton==1.90.0") from exc
    source_version = getattr(hamilton, "__version__", ())
    imported = (
        source_version if isinstance(source_version, str) else ".".join(map(str, source_version))
    )
    if installed != SUPPORTED_HAMILTON_VERSION or imported != SUPPORTED_HAMILTON_VERSION:
        raise RuntimeError(
            f"Unsupported Hamilton version: distribution={installed}, imported={imported}; "
            f"requires apache-hamilton=={SUPPORTED_HAMILTON_VERSION}"
        )
    try:
        sdax_version = metadata.version("sdax")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("sdax-hamilton requires sdax==0.7.2") from exc
    if sdax_version != SUPPORTED_SDAX_VERSION:
        raise RuntimeError(
            f"Unsupported SDAX version: {sdax_version}; requires sdax=={SUPPORTED_SDAX_VERSION}"
        )


def _decorators(fn):
    return tuple(
        modifier
        for stage in _LIFECYCLES
        for modifier in getattr(fn, stage.get_lifecycle_name(), ())
    )


def _excluded(fn):
    return any(type(modifier) is _EXCLUDED for modifier in _decorators(fn))


_CapturedFact = tuple[GeneratedRole, Callable[..., Any], bool]
_BORROWING_ROLES = frozenset(
    (GeneratedRole.PROJECTION, GeneratedRole.VALIDATION_RAW, GeneratedRole.VALIDATION_GATE)
)


class _ProvenanceCapture:
    """Construction-local facts captured from copied Hamilton modifiers."""

    def __init__(
        self,
        owned: Collection[Callable[..., Any]],
    ) -> None:
        self.owned = frozenset(owned)
        self._clones: dict[Callable[..., Any], Callable[..., Any]] = {}
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
    ) -> None:
        mount, _ = self._mount()
        callable_ = entry.callable
        self._pending[(mount, id(callable_))] = (
            callable_,
            (role, declaration, actual_call),
        )

    def _handoff(
        self,
        entry: node.Node,
        mount: object,
        fact: _CapturedFact,
    ) -> None:
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
                return GeneratedRole.VALUE, declaration, True
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
            actual_call = True if incoming is None else incoming[2]
            generated = list(transform(entry, configuration, fn))
            self._remember(
                generated[0], GeneratedRole.VALUE, declaration, actual_call=actual_call
            )
            for projection in generated[1:]:
                self._remember(
                    projection,
                    GeneratedRole.PROJECTION,
                    declaration,
                    actual_call=False,
                )
            return generated

        self._install_method(
            modifier,
            "transform_node",
            MethodType(transform_with_capture, modifier),
        )

    def _instrument_validation(
        self, modifier: BaseDataValidationDecorator, declaration: Callable[..., Any]
    ) -> None:
        transform = modifier.transform_node

        def transform_with_capture(
            instance: BaseDataValidationDecorator,
            entry: node.Node,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> list[node.Node]:
            incoming = self._fact_from_callable(entry)
            actual_call = True if incoming is None else incoming[2]
            generated = list(transform(entry, configuration, fn))
            for evidence in generated[:-2]:
                self._remember(
                    evidence,
                    GeneratedRole.VALIDATION_EVIDENCE,
                    declaration,
                    actual_call=False,
                )
            self._remember(
                generated[-2],
                GeneratedRole.VALIDATION_GATE,
                declaration,
                actual_call=False,
            )
            self._remember(
                generated[-1],
                GeneratedRole.VALIDATION_RAW,
                declaration,
                actual_call=actual_call,
            )
            return generated

        self._install_method(
            modifier,
            "transform_node",
            MethodType(transform_with_capture, modifier),
        )

    def _instrument_resolver(
        self, modifier: resolve_from_config, declaration: Callable[..., Any]
    ) -> None:
        resolve = modifier.resolve

        def resolve_with_capture(
            instance: resolve_from_config,
            configuration: dict[str, Any],
            fn: Callable[..., Any],
        ) -> base.NodeTransformLifecycle:
            resolved = copy(resolve(configuration, fn))
            if type(resolved) is not check_output_custom:
                raise ValueError(
                    f"{declaration.__name__}: feasibility resolver must return "
                    "check_output_custom"
                )
            self._instrument_validation(resolved, declaration)
            return resolved

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

    def _instrument_modifier(
        self, snapshot: base.NodeTransformLifecycle, declaration: Callable[..., Any]
    ) -> base.NodeTransformLifecycle:
        if type(snapshot) is parameterized_subdag:
            self._instrument_parameterized_subdag(snapshot, declaration)
        elif type(snapshot) is extract_fields:
            self._instrument_extract_fields(snapshot, declaration)
        elif type(snapshot) is resolve_from_config:
            self._instrument_resolver(snapshot, declaration)
        elif type(snapshot) is check_output_custom:
            self._instrument_validation(snapshot, declaration)
        wrap_result = (
            wrap_lifecycle if snapshot.get_lifecycle_name() == "dynamic" else None
        )
        return wrap_lifecycle(snapshot, wrap_result=wrap_result)

    def clone(self, fn: Callable[..., Any]) -> Callable[..., Any]:
        existing = self._clones.get(fn)
        if existing is not None:
            return existing
        clone = _copy_function(fn, _wrap_lifecycles=False)
        self._clones[fn] = clone
        self._originals[clone] = fn
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
                return GeneratedRole.VALUE, declaration, True
        raise AssertionError(f"Unattributed resolved Hamilton node {entry.name}")

    def borrow_from(
        self,
        resolved: Collection[node.Node],
        facts: Mapping[str, _CapturedFact],
    ) -> dict[str, frozenset[str]]:
        by_name = {entry.name: entry for entry in resolved}
        owners = {
            name
            for name, (_, declaration, actual_call) in facts.items()
            if actual_call and declaration in self.owned
        }
        borrowed = {}
        for name, (role, _, _) in facts.items():
            if role not in _BORROWING_ROLES:
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
                else:
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
        self._originals.clear()
        self._mounts.clear()


def _copy_function(
    fn: Callable[..., Any], *, _wrap_lifecycles: bool = True
) -> Callable[..., Any]:
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
                if _wrap_lifecycles:
                    wrap_result = (
                        wrap_lifecycle if snapshot.get_lifecycle_name() == "dynamic" else None
                    )
                    snapshot = wrap_lifecycle(snapshot, wrap_result=wrap_result)
                modifiers.append(snapshot)
            setattr(clone, key, modifiers)
    clone.__module__ = fn.__module__
    clone.__qualname__ = fn.__qualname__
    clone.__doc__ = fn.__doc__
    return clone


def _validate_bindings(fn, modifier, hints, parameters):
    for output, bindings in modifier.parameterization.items():
        requirements: dict[str, list[tuple[Any, bool]]] = {}
        for name, binding in bindings.items():
            if name not in parameters:
                raise ValueError(f"{fn.__name__}: unknown bound parameter {name}")
            if type(binding) is LiteralDependency:
                if not accepts(binding.value, hints[name]):
                    raise TypeError(f"{fn.__name__}.{name}: bound literal has wrong type")
            elif type(binding) is UpstreamDependency:
                if not isinstance(binding.source, str) or not binding.source:
                    raise ValueError(f"{fn.__name__}.{name}: source must name a node")
                if parameters[name].default is not inspect.Parameter.empty:
                    raise ValueError(f"{fn.__name__}.{name}: optional source rebinding unsupported")
                requirements.setdefault(binding.source, []).append((hints[name], False))
            else:
                raise ValueError(f"{fn.__name__}.{name}: grouped/config binding unsupported")
        for name in parameters:
            if name not in bindings:
                optional = parameters[name].default is not inspect.Parameter.empty
                requirements.setdefault(name, []).append((hints[name], optional))
        if _PARAMETERIZE_INTERNAL_INPUTS.intersection(requirements):
            raise ValueError(
                f"{fn.__name__}/{output}: binding collides with Hamilton wrapper parameter"
            )
        # Hamilton merges repeated sources into one input. Do not lose any of
        # the original parameter contracts at that merge boundary.
        for contracts in requirements.values():
            if any(typ != contracts[0][0] for typ, _ in contracts):
                raise TypeError(
                    f"{fn.__name__}/{output}: merged source has different parameter types"
                )
            if len(contracts) > 1 and any(optional for _, optional in contracts):
                raise ValueError(
                    f"{fn.__name__}/{output}: merged source has optional parameter contract"
                )


def _validate_declaration(fn, supported=_SUPPORTED):
    if _excluded(fn):
        return
    if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        raise TypeError(f"{fn.__name__}: generator and async-generator functions unsupported")
    hints = get_type_hints(fn, include_extras=True)
    parameters = inspect.signature(fn).parameters
    for name, parameter in parameters.items():
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD, parameter.KEYWORD_ONLY):
            raise TypeError(f"{fn.__name__}: variadic and positional-only parameters unsupported")
        if name not in hints:
            raise TypeError(f"{fn.__name__}.{name}: missing type")
        validate_type(hints[name])
        if parameter.default is not inspect.Parameter.empty and not accepts(
            parameter.default, hints[name]
        ):
            raise TypeError(f"{fn.__name__}.{name}: invalid default")
    if "return" not in hints:
        raise TypeError(f"{fn.__name__}: missing return type")
    validate_type(hints["return"])
    for modifier in _decorators(fn):
        if type(modifier) not in supported:
            raise ValueError(
                f"{fn.__name__}: unsupported Hamilton decorator {type(modifier).__name__}"
            )
        if isinstance(modifier, parameterize):
            _validate_bindings(fn, modifier, hints, parameters)


def _declaration_closure(declarations, supported):
    collected = []
    seen = set()
    stack = list(reversed(declarations))
    while stack:
        declaration = stack.pop()
        if declaration in seen:
            continue
        seen.add(declaration)
        _validate_declaration(declaration, supported)
        collected.append(declaration)
        for modifier in _decorators(declaration):
            if type(modifier) is parameterized_subdag:
                for nested in reversed(modifier.load_from):
                    if not isinstance(nested, FunctionType):
                        raise ValueError(
                            f"{declaration.__name__}: parameterized subdag requires "
                            "function declarations"
                        )
                    stack.append(nested)
    return tuple(collected)


def _release_type(fn):
    if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        raise TypeError(
            f"{fn.__name__}: generator and async-generator shutdown functions unsupported"
        )
    if _decorators(fn) or hasattr(fn, "__sdax_execution__"):
        raise ValueError(f"{fn.__name__}: shutdown cannot carry Hamilton or execution decorators")
    parameters = tuple(inspect.signature(fn).parameters.values())
    if (
        len(parameters) != 1
        or parameters[0].kind
        not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        )
        or parameters[0].default is not inspect.Parameter.empty
    ):
        raise TypeError(
            f"{fn.__name__}: shutdown requires one required positional Acquisition[T] argument"
        )
    hints = get_type_hints(fn, include_extras=True)
    annotation = hints.get(parameters[0].name)
    if get_origin(annotation) is not Acquisition or len(get_args(annotation)) != 1:
        raise TypeError(f"{fn.__name__}: shutdown parameter must be Acquisition[T]")
    inner_type = get_args(annotation)[0]
    validate_type(inner_type)
    if hints.get("return") is not type(None):
        raise TypeError(f"{fn.__name__}: shutdown must return None")
    return inner_type


def _targets(target, names, label):
    if target is None:
        if len(names) != 1:
            raise ValueError(f"{label}: expanded declaration requires explicit target_")
        return frozenset(names)
    selected = (target,) if isinstance(target, str) else target
    if (
        not isinstance(selected, tuple)
        or not selected
        or any(not isinstance(name, str) for name in selected)
    ):
        raise TypeError(f"{label}: target_ must be a name or nonempty tuple of names")
    if len(set(selected)) != len(selected):
        raise ValueError(f"{label}: duplicate target_")
    missing = set(selected) - names
    if missing:
        raise ValueError(f"{label}: targets not generated: {sorted(missing)}")
    return frozenset(selected)


def _lower_inputs(entry: node.Node) -> Mapping[str, InputSpec]:
    inputs = {}
    for name, (typ, dependency_type) in entry.input_types.items():
        validate_type(typ)
        default = entry.default_parameter_values.get(name, MISSING)
        if dependency_type is node.DependencyType.OPTIONAL and default is MISSING:
            raise ValueError(f"{entry.name}.{name}: transformed optional default unavailable")
        inputs[name] = InputSpec(typ, default)
    return MappingProxyType(inputs)


def compile_modules(modules, configuration, *, _supported=_SUPPORTED):
    """Resolve declarations once, preserving ownership before config replacement."""
    _check_version()
    if not modules or any(not isinstance(module, ModuleType) for module in modules):
        raise TypeError("Driver requires one or more Python modules")
    functions = dict.fromkeys(fn for module in modules for _, fn in find_functions(module))
    declarations = tuple(fn for fn in functions if not hasattr(fn, "__sdax_shutdown__"))
    all_declarations = _declaration_closure(declarations, _supported)
    owned: dict[
        FunctionType, list[tuple[FunctionType, str | tuple[str, ...] | None, Policy, Any]]
    ] = {}
    for release in functions:
        if not hasattr(release, "__sdax_shutdown__"):
            continue
        owner, target, policy = release.__sdax_shutdown__
        if owner not in all_declarations:
            raise ValueError(f"{release.__name__}: owner not discovered in supplied modules")
        release_type = _release_type(release)
        owned.setdefault(owner, []).append((release, target, policy, release_type))
    for owner in owned:
        if _excluded(owner):
            raise ValueError(f"{owner.__name__}: excluded declaration cannot own a shutdown")

    capture = _ProvenanceCapture(owned)
    release_specs = {
        owner: [
            (capture.clone(release), target, policy, release_type)
            for release, target, policy, release_type in releases
        ]
        for owner, releases in owned.items()
    }

    resolved = {}
    captured_facts = {}
    policies = {}
    shutdowns = {}
    try:
        for fn in declarations:
            if _excluded(fn):
                continue
            expanded = tuple(_resolve_nodes(capture.clone(fn), dict(configuration)))
            if not expanded:
                continue
            facts = {entry.name: capture.fact(entry) for entry in expanded}
            names = {entry.name for entry in expanded}
            if len(names) != len(expanded):
                raise ValueError(f"{fn.__name__}: duplicate generated Hamilton node")
            policy, target = getattr(fn, "__sdax_execution__", (Policy(), None))
            policy_targets = (
                _targets(target, names, fn.__name__)
                if hasattr(fn, "__sdax_execution__")
                else frozenset()
            )
            owners = {
                declaration
                for _, declaration, actual_call in facts.values()
                if actual_call and declaration in release_specs
            }
            for owner in owners:
                candidates = frozenset(
                    name
                    for name, (_, declaration, actual_call) in facts.items()
                    if actual_call and declaration is owner
                )
                for release, target, release_policy, release_type in release_specs[owner]:
                    selected = (
                        _targets(target, candidates, release.__name__)
                        if target is not None or owner is fn
                        else candidates
                    )
                    for name in selected:
                        if name in shutdowns:
                            raise ValueError(f"{name}: duplicate shutdown declaration")
                        shutdowns[name] = (release, release_policy, release_type)
            for entry in expanded:
                if entry.name in resolved:
                    raise ValueError(f"Duplicate Hamilton node {entry.name}")
                if entry.node_role is not node.NodeType.STANDARD:
                    raise ValueError(f"{entry.name}: dynamic Hamilton nodes unsupported")
                validate_type(entry.type)
                resolved[entry.name] = entry
                captured_facts[entry.name] = facts[entry.name]
                policies[entry.name] = policy if entry.name in policy_targets else Policy()

        borrow_from = capture.borrow_from(tuple(resolved.values()), captured_facts)
        specs = {}
        for name, entry in resolved.items():
            release, release_policy = None, Policy()
            if name in shutdowns:
                release, release_policy, release_type = shutdowns[name]
                if not compatible(entry.type, release_type):
                    raise TypeError(
                        f"{release.__name__}: shutdown Acquisition type does not accept {name}"
                    )
            role, declaration, actual_call = captured_facts[name]
            specs[name] = NodeSpec(
                name=name,
                fn=entry.callable,
                output_type=entry.type,
                inputs=_lower_inputs(entry),
                tags=entry.tags,
                policy=policies[name],
                release=release,
                release_policy=release_policy,
                origin=f"{declaration.__module__}.{declaration.__qualname__}",
                ownership_required=actual_call and declaration in release_specs,
                role=role,
                borrow_from=borrow_from.get(name, frozenset()),
            )

        # Hamilton performs its native edge compatibility checks. The mutable graph
        # is discarded; original specs preserve config-replaced ownership for Plan.
        graph.update_dependencies(
            {name: entry for name, entry in resolved.items() if name not in configuration},
            LifecycleAdapterSet(),
            reset_dependencies=False,
        )
        return MappingProxyType(specs)
    finally:
        capture.finalize()
