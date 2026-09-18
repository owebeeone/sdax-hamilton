"""Version-bounded translation of real Hamilton declarations into owned node specs.

Hamilton's internal APIs are deliberately confined here. No Hamilton executor or
mutable graph escapes this boundary; SDAX receives only our immutable node model.
"""

import inspect
from collections.abc import Mapping
from importlib import metadata
from types import FunctionType, MappingProxyType, ModuleType
from typing import Any, cast, get_args, get_origin, get_type_hints

import hamilton
from hamilton import graph, node
from hamilton.function_modifiers import base as base  # noqa: F401 -- retained test seam
from hamilton.function_modifiers import (
    config,
    hamilton_exclude,
    inject,
    parameterize,
    parameterize_sources,
    parameterize_values,
    parameterized_inputs,
    parametrized,
    parametrized_input,
    tag,
    tag_outputs,
)
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.function_modifiers.metadata import RayRemote, SchemaOutput, cache
from hamilton.lifecycle.base import LifecycleAdapterSet

from ._construction import resolve_nodes as _resolve_nodes
from ._discovery import discover_declarations, discover_shutdowns_for
from ._hamilton_provenance import (  # noqa: F401 -- retained private compatibility seam
    _LIFECYCLES,
    _copy_function,
    _ProvenanceCapture,
)
from ._model import MISSING, InputSpec, NodeSpec
from ._types import accepts, compatible, validate_type
from .declarations import Acquisition, Policy

SUPPORTED_HAMILTON_VERSION = "1.90.0"
SUPPORTED_SDAX_VERSION = "0.7.2"
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


def _declaration_closure(modules, supported):
    snapshot = discover_declarations(modules)
    declarations = (*snapshot.roots, *snapshot.nested)
    for declaration in declarations:
        _validate_declaration(declaration, supported)
    return snapshot


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


def _actual_targets(target, owner, root, entries, facts, label):
    candidates = frozenset(
        name
        for name, fact in facts.items()
        if fact.actual_call and fact.declaration is owner
    )
    if target is None:
        if owner is root:
            return _targets(None, candidates, label)
        return candidates

    selected = (target,) if isinstance(target, str) else target
    if (
        not isinstance(selected, tuple)
        or not selected
        or any(not isinstance(name, str) for name in selected)
    ):
        raise TypeError(f"{label}: target_ must be a name or nonempty tuple of names")
    if len(set(selected)) != len(selected):
        raise ValueError(f"{label}: duplicate target_")

    by_name = {entry.name: entry for entry in entries}
    result = set()
    for public_name in selected:
        direct = {
            name
            for name in candidates
            if facts[name].public_name == public_name or name == public_name
        }
        if direct:
            result.update(direct)
            continue
        aliases = {
            name
            for name, fact in facts.items()
            if fact.declaration is owner
            and (fact.public_name == public_name or name == public_name)
        }
        found = set()
        for alias in aliases:
            mount = facts[alias].mount
            visited = set()
            stack = [alias]
            while stack:
                name = stack.pop()
                if name in visited or name not in by_name:
                    continue
                visited.add(name)
                if name in candidates and facts[name].mount is mount:
                    found.add(name)
                stack.extend(by_name[name].input_types)
        if not found:
            raise ValueError(f"{label}: targets not generated: {[public_name]}")
        result.update(found)
    return frozenset(result)


def _lower_inputs(
    entry: node.Node,
    captured: Mapping[str, InputSpec] = MappingProxyType({}),
) -> Mapping[str, InputSpec]:
    unknown = captured.keys() - entry.input_types.keys()
    if unknown:
        raise AssertionError(
            f"Captured contracts are not final inputs of {entry.name}: {sorted(unknown)}"
        )
    inputs = {}
    for name, (typ, dependency_type) in entry.input_types.items():
        validate_type(typ)
        contract = captured.get(name)
        if contract is None:
            default = entry.default_parameter_values.get(name, MISSING)
            if dependency_type is node.DependencyType.OPTIONAL and default is MISSING:
                raise ValueError(
                    f"{entry.name}.{name}: transformed optional default unavailable"
                )
            inputs[name] = InputSpec(typ, default)
            continue
        requirements = contract.effective_requirements
        for requirement in requirements:
            validate_type(requirement)
        default = (
            contract.default
            if dependency_type is node.DependencyType.OPTIONAL
            else MISSING
        )
        if default is not MISSING and not all(
            accepts(default, requirement) for requirement in requirements
        ):
            raise TypeError(f"{entry.name}.{name}: captured default has wrong type")
        inputs[name] = InputSpec(typ, default, requirements)
    return MappingProxyType(inputs)


def compile_modules(modules, configuration, *, _supported=_SUPPORTED):
    """Resolve declarations once, preserving ownership before config replacement."""
    _check_version()
    if not modules or any(not isinstance(module, ModuleType) for module in modules):
        raise TypeError("Driver requires one or more Python modules")
    discovery = _declaration_closure(modules, _supported)
    declarations = discovery.roots
    all_declarations = (*discovery.roots, *discovery.nested)
    known_declarations = set(all_declarations)
    owned: dict[
        FunctionType, list[tuple[FunctionType, str | tuple[str, ...] | None, Policy, Any]]
    ] = {}
    for release in discovery.shutdowns:
        owner, target, policy = release.__sdax_shutdown__
        if owner not in all_declarations:
            raise ValueError(f"{release.__name__}: owner not discovered in supplied modules")
        release_type = _release_type(release)
        owned.setdefault(owner, []).append((release, target, policy, release_type))
    for owner in owned:
        if _excluded(owner):
            raise ValueError(f"{owner.__name__}: excluded declaration cannot own a shutdown")
    execution_specs = {
        declaration: declaration.__sdax_execution__
        for declaration in all_declarations
        if hasattr(declaration, "__sdax_execution__")
    }

    validated_declarations = set(all_declarations)

    def validate_captured(declaration):
        if declaration in validated_declarations:
            return
        _validate_declaration(declaration, _supported)
        validated_declarations.add(declaration)

    capture = _ProvenanceCapture(
        owned,
        _supported,
        validate_declaration=validate_captured,
    )
    release_specs = {
        owner: [
            (capture.clone(release, validate=False), target, policy, release_type)
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
            with capture.resolving(fn):
                expanded = tuple(_resolve_nodes(capture.clone(fn), dict(configuration)))
            if not expanded:
                continue
            facts = {entry.name: capture.fact(entry) for entry in expanded}
            undiscovered = tuple(
                dict.fromkeys(
                    fact.declaration
                    for fact in facts.values()
                    if fact.actual_call and fact.declaration not in known_declarations
                )
            )
            if any(not isinstance(declaration, FunctionType) for declaration in undiscovered):
                raise ValueError("generated declaration has no function identity")
            helper_functions = cast(tuple[FunctionType, ...], undiscovered)
            if helper_functions:
                helper_releases = discover_shutdowns_for(helper_functions)
                helper_owners = tuple(
                    dict.fromkeys(
                        getattr(release, "__sdax_shutdown__")[0]
                        for release in helper_releases
                    )
                )
                all_declarations = (*all_declarations, *helper_functions)
                known_declarations.update(helper_functions)
                capture.owned = frozenset((*capture.owned, *helper_owners))
                for owner in helper_functions:
                    if hasattr(owner, "__sdax_execution__"):
                        execution_specs[owner] = owner.__sdax_execution__
                for release in helper_releases:
                    owner, target, policy = getattr(release, "__sdax_shutdown__")
                    release_type = _release_type(release)
                    owned.setdefault(owner, []).append((release, target, policy, release_type))
                    release_specs.setdefault(owner, []).append(
                        (capture.clone(release, validate=False), target, policy, release_type)
                    )
            generated_names = {entry.name for entry in expanded}
            if len(generated_names) != len(expanded):
                raise ValueError(f"{fn.__name__}: duplicate generated Hamilton node")
            owners = {
                fact.declaration
                for fact in facts.values()
                if fact.actual_call and fact.declaration in release_specs
            }
            for owner in owners:
                for release, target, release_policy, release_type in release_specs[owner]:
                    selected = _actual_targets(
                        target,
                        owner,
                        fn,
                        expanded,
                        facts,
                        release.__name__,
                    )
                    for name in selected:
                        if name in shutdowns:
                            raise ValueError(f"{name}: duplicate shutdown declaration")
                        shutdowns[name] = (release, release_policy, release_type)
            policy_owners = {
                fact.declaration
                for fact in facts.values()
                if fact.actual_call and fact.declaration in execution_specs
            }
            for owner in policy_owners:
                policy, target = execution_specs[owner]
                for name in _actual_targets(
                    target,
                    owner,
                    fn,
                    expanded,
                    facts,
                    owner.__name__,
                ):
                    if name in policies:
                        raise ValueError(f"{name}: duplicate execution declaration")
                    policies[name] = policy
            for entry in expanded:
                if entry.name in resolved:
                    raise ValueError(f"Duplicate Hamilton node {entry.name}")
                if entry.node_role is not node.NodeType.STANDARD:
                    raise ValueError(f"{entry.name}: dynamic Hamilton nodes unsupported")
                validate_type(entry.type)
                resolved[entry.name] = entry
                captured_facts[entry.name] = facts[entry.name]

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
            fact = captured_facts[name]
            specs[name] = NodeSpec(
                name=name,
                fn=entry.callable,
                output_type=entry.type,
                inputs=_lower_inputs(entry, fact.input_contracts),
                tags=entry.tags,
                policy=policies.get(name, Policy()),
                release=release,
                release_policy=release_policy,
                origin=f"{fact.declaration.__module__}.{fact.declaration.__qualname__}",
                ownership_required=fact.actual_call and fact.declaration in release_specs,
                role=fact.role,
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
