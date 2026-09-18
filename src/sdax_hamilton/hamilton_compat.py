"""Version-bounded translation of real Hamilton declarations into owned node specs.

Hamilton's internal APIs are deliberately confined here. No Hamilton executor or
mutable graph escapes this boundary; SDAX receives only our immutable node model.
"""

import inspect
from copy import copy
from importlib import metadata
from types import FunctionType, MappingProxyType, ModuleType
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
    parametrized,
    parametrized_input,
    tag,
    tag_outputs,
)
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.function_modifiers.metadata import RayRemote, SchemaOutput, cache
from hamilton.graph_utils import find_functions
from hamilton.lifecycle.base import LifecycleAdapterSet

from ._model import MISSING, InputSpec, NodeSpec
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


def _copy_function(fn):
    # config.resolve renames its argument. Isolate that operation from user modules.
    clone = FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
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


def _validate_declaration(fn):
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
        if type(modifier) not in _SUPPORTED:
            raise ValueError(
                f"{fn.__name__}: unsupported Hamilton decorator {type(modifier).__name__}"
            )
        if isinstance(modifier, parameterize):
            _validate_bindings(fn, modifier, hints, parameters)


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


def compile_modules(modules, configuration):
    """Resolve declarations once, preserving ownership before config replacement."""
    _check_version()
    if not modules or any(not isinstance(module, ModuleType) for module in modules):
        raise TypeError("Driver requires one or more Python modules")
    functions = dict.fromkeys(fn for module in modules for _, fn in find_functions(module))
    declarations = tuple(fn for fn in functions if not hasattr(fn, "__sdax_shutdown__"))
    owned: dict[
        FunctionType, list[tuple[FunctionType, str | tuple[str, ...] | None, Policy, Any]]
    ] = {}
    for release in functions:
        if not hasattr(release, "__sdax_shutdown__"):
            continue
        owner, target, policy = release.__sdax_shutdown__
        if owner not in declarations:
            raise ValueError(f"{release.__name__}: owner not discovered in supplied modules")
        release_type = _release_type(release)
        owned.setdefault(owner, []).append((_copy_function(release), target, policy, release_type))
    for owner in owned:
        if _excluded(owner):
            raise ValueError(f"{owner.__name__}: excluded declaration cannot own a shutdown")

    resolved, specs = {}, {}
    for fn in declarations:
        if _excluded(fn):
            continue
        _validate_declaration(fn)
        expanded = tuple(base.resolve_nodes(_copy_function(fn), dict(configuration)))
        if not expanded:
            continue
        names = {entry.name for entry in expanded}
        if len(names) != len(expanded):
            raise ValueError(f"{fn.__name__}: duplicate generated Hamilton node")
        policy, target = getattr(fn, "__sdax_execution__", (Policy(), None))
        policy_targets = (
            _targets(target, names, fn.__name__)
            if hasattr(fn, "__sdax_execution__")
            else frozenset()
        )
        shutdown_targets = {}
        for release, target, release_policy, release_type in owned.get(fn, ()):
            for name in _targets(target, names, release.__name__):
                if name in shutdown_targets:
                    raise ValueError(f"{name}: duplicate shutdown declaration")
                shutdown_targets[name] = (release, release_policy, release_type)
        for entry in expanded:
            if entry.name in resolved:
                raise ValueError(f"Duplicate Hamilton node {entry.name}")
            if entry.node_role is not node.NodeType.STANDARD:
                raise ValueError(f"{entry.name}: dynamic Hamilton nodes unsupported")
            validate_type(entry.type)
            inputs = {}
            for name, (typ, dependency_type) in entry.input_types.items():
                validate_type(typ)
                default = entry.default_parameter_values.get(name, MISSING)
                if dependency_type is node.DependencyType.OPTIONAL and default is MISSING:
                    raise ValueError(
                        f"{entry.name}.{name}: transformed optional default unavailable"
                    )
                inputs[name] = InputSpec(typ, default)
            release, release_policy = None, Policy()
            if entry.name in shutdown_targets:
                release, release_policy, release_type = shutdown_targets[entry.name]
                if not compatible(entry.type, release_type):
                    raise TypeError(
                        f"{release.__name__}: shutdown Acquisition type does not accept {entry.name}"
                    )
            specs[entry.name] = NodeSpec(
                name=entry.name,
                fn=entry.callable,
                output_type=entry.type,
                inputs=MappingProxyType(inputs),
                tags=entry.tags,
                policy=policy if entry.name in policy_targets else Policy(),
                release=release,
                release_policy=release_policy,
                origin=f"{fn.__module__}.{fn.__qualname__}",
                ownership_required=fn in owned,
            )
            resolved[entry.name] = entry

    # Hamilton performs its native edge compatibility checks. The mutable graph
    # is discarded; original specs preserve config-replaced ownership for Plan.
    graph.update_dependencies(
        {name: entry for name, entry in resolved.items() if name not in configuration},
        LifecycleAdapterSet(),
        reset_dependencies=False,
    )
    return MappingProxyType(specs)
