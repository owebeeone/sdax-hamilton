"""Bounded source/value/group binding capture for the Hamilton compatibility layer."""

import inspect
from collections.abc import Mapping
from copy import copy
from typing import Any, get_origin

from hamilton.function_modifiers.dependencies import (
    GroupedDictDependency,
    GroupedListDependency,
    LiteralDependency,
    UpstreamDependency,
)
from hamilton.function_modifiers.expanders import (
    ParameterizedExtract,
    inject,
    parameterize,
    parameterize_extract_columns,
    parameterize_sources,
    parameterize_values,
    parameterized_inputs,
    parametrized,
    parametrized_input,
)

from ._model import MISSING, InputSpec
from ._types import accepts, validate_type

_INTERNAL_INPUTS = frozenset(
    (
        "upstream_dependencies",
        "literal_dependencies",
        "grouped_list_dependencies",
        "grouped_dict_dependencies",
        "former_inputs",
    )
)
_PARAMETERIZE_TYPES = frozenset(
    (
        parameterize,
        parameterize_sources,
        parameterize_values,
        parametrized,
        parametrized_input,
        parameterized_inputs,
        inject,
    )
)


def capture_bindings(
    fn: Any,
    modifier: Any,
    hints: Mapping[str, Any],
    parameters: Mapping[str, inspect.Parameter],
) -> dict[str, dict[str, InputSpec]]:
    """Return original contracts keyed by each pinned generated output and input name."""
    if type(modifier) in _PARAMETERIZE_TYPES:
        mappings = {}
        for output, bindings in modifier.parameterization.items():
            name = fn.__name__ if output == parameterize.PLACEHOLDER_PARAM_NAME else output
            mappings[name] = bindings
    elif type(modifier) is parameterize_extract_columns:
        mappings = {}
        for index, extract in enumerate(modifier.extract_config):
            if type(extract) is not ParameterizedExtract:
                raise ValueError(f"{fn.__name__}: invalid parameterize_extract_columns binding")
            mappings[f"{fn.__name__}__{index}"] = extract.input_mapping
    else:
        return {}
    return {
        output: _capture_output(fn, bindings, hints, parameters)
        for output, bindings in mappings.items()
    }


def snapshot_binding_containers(modifier: Any) -> None:
    """Copy the finite mutable binding containers on an already copied modifier."""
    if type(modifier) in _PARAMETERIZE_TYPES:
        if type(modifier.parameterization) is not dict:
            raise ValueError("parameterize binding map must be a dict")
        modifier.parameterization = {
            output: _snapshot_binding_map(bindings)
            for output, bindings in modifier.parameterization.items()
        }
    elif type(modifier) is parameterize_extract_columns:
        if type(modifier.extract_config) is not tuple:
            raise ValueError("parameterize_extract_columns bindings must be a tuple")
        extracts = []
        for extract in modifier.extract_config:
            if type(extract) is not ParameterizedExtract:
                raise ValueError("invalid parameterize_extract_columns binding")
            snapshot = copy(extract)
            snapshot.input_mapping = _snapshot_binding_map(extract.input_mapping)
            extracts.append(snapshot)
        modifier.extract_config = tuple(extracts)


def _snapshot_binding_map(bindings: Any) -> dict[str, Any]:
    if type(bindings) is not dict:
        raise ValueError("binding map must be a dict")
    return {name: _snapshot_binding(binding) for name, binding in bindings.items()}


def _snapshot_binding(binding: Any) -> Any:
    if type(binding) in (LiteralDependency, UpstreamDependency):
        return copy(binding)
    if type(binding) is GroupedListDependency:
        if type(binding.sources) is not list:
            raise ValueError("grouped list binding must contain a list")
        snapshot = copy(binding)
        snapshot.sources = [_snapshot_binding(item) for item in binding.sources]
        return snapshot
    if type(binding) is GroupedDictDependency:
        if type(binding.sources) is not dict:
            raise ValueError("grouped dict binding must contain a dict")
        snapshot = copy(binding)
        snapshot.sources = {
            name: _snapshot_binding(item) for name, item in binding.sources.items()
        }
        return snapshot
    return copy(binding)


def _capture_output(
    fn: Any,
    bindings: Any,
    hints: Mapping[str, Any],
    parameters: Mapping[str, inspect.Parameter],
) -> dict[str, InputSpec]:
    if type(bindings) is not dict:
        raise ValueError(f"{fn.__name__}: binding map must be a dict")
    unknown = set(bindings) - parameters.keys()
    if unknown:
        raise ValueError(f"{fn.__name__}: unknown bound parameter {sorted(unknown)[0]}")
    requirements: dict[str, list[Any]] = {}
    defaults: dict[str, list[object]] = {}
    required: set[str] = set()
    unbound = set(parameters) - set(bindings)
    literal_fallbacks = {
        name: binding.value
        for name, binding in bindings.items()
        if type(binding) is LiteralDependency
    }
    for name, parameter in parameters.items():
        if name not in hints:
            raise TypeError(f"{fn.__name__}.{name}: missing type")
        annotation = hints[name]
        validate_type(annotation)
        if name not in bindings:
            requirements.setdefault(name, []).append(annotation)
            if parameter.default is not inspect.Parameter.empty:
                _record_default(name, parameter.default, defaults)
            else:
                required.add(name)
            continue
        binding = bindings[name]
        if type(binding) is LiteralDependency:
            if not accepts(binding.value, annotation):
                raise TypeError(f"{fn.__name__}.{name}: bound literal has wrong type")
            continue
        if type(binding) is UpstreamDependency:
            _source_requirement(
                fn,
                binding,
                annotation,
                requirements,
                defaults,
                required,
                parameters,
                unbound,
                literal_fallbacks,
                fallback=parameter.default,
            )
            continue
        if type(binding) in (GroupedListDependency, GroupedDictDependency):
            expected_origin = list if type(binding) is GroupedListDependency else dict
            if get_origin(annotation) is not expected_origin:
                raise ValueError(f"{fn.__name__}.{name}: invalid grouped binding annotation")
            component = binding.resolve_dependency_type(annotation, name)
            validate_type(component)
            for item in _group_items(fn, binding):
                if type(item) is LiteralDependency:
                    if not accepts(item.value, component):
                        raise TypeError(f"{fn.__name__}.{name}: bound literal has wrong type")
                else:
                    _source_requirement(
                        fn,
                        item,
                        component,
                        requirements,
                        defaults,
                        required,
                        parameters,
                        unbound,
                        literal_fallbacks,
                    )
            continue
        raise ValueError(f"{fn.__name__}.{name}: grouped/config binding unsupported")
    if _INTERNAL_INPUTS.intersection(requirements):
        raise ValueError(f"{fn.__name__}: binding collides with Hamilton wrapper parameter")
    captured = {}
    for name, contracts in requirements.items():
        default = MISSING if name in required else _merged_default(fn, name, defaults.get(name, []))
        if default is not MISSING and not all(accepts(default, contract) for contract in contracts):
            raise TypeError(f"{fn.__name__}.{name}: bound default has wrong type")
        captured[name] = InputSpec(contracts[0], default, tuple(contracts))
    return captured


def _source_requirement(
    fn: Any,
    binding: UpstreamDependency,
    annotation: Any,
    requirements: dict[str, list[Any]],
    defaults: dict[str, list[object]],
    required: set[str],
    parameters: Mapping[str, inspect.Parameter],
    unbound: set[str],
    literal_fallbacks: Mapping[str, object],
    *,
    fallback: object = inspect.Parameter.empty,
) -> None:
    source = binding.source
    if not isinstance(source, str) or not source:
        raise ValueError(f"{fn.__name__}: source must name a node")
    requirements.setdefault(source, []).append(annotation)
    source_parameter = parameters.get(source)
    if source in literal_fallbacks:
        _record_default(source, literal_fallbacks[source], defaults)
    elif source_parameter is not None and source in unbound:
        if source_parameter.default is inspect.Parameter.empty:
            required.add(source)
        else:
            _record_default(source, source_parameter.default, defaults)
    elif fallback is inspect.Parameter.empty:
        required.add(source)
    else:
        _record_default(source, fallback, defaults)


def _record_default(name: str, default: object, defaults: dict[str, list[object]]) -> None:
    defaults.setdefault(name, []).append(default)


def _merged_default(fn: Any, name: str, defaults: list[object]) -> object:
    if not defaults:
        return MISSING
    default = defaults[0]
    if any(candidate is not default for candidate in defaults[1:]):
        raise ValueError(f"{fn.__name__}.{name}: conflicting merged source defaults")
    return default


def _group_items(fn: Any, binding: GroupedListDependency | GroupedDictDependency) -> tuple[Any, ...]:
    sources = binding.sources
    if type(binding) is GroupedListDependency:
        if type(sources) is not list:
            raise ValueError(f"{fn.__name__}: grouped binding must contain direct source/value items")
        items = tuple(sources)
    elif type(sources) is dict:
        items = tuple(sources.values())
    else:
        raise ValueError(f"{fn.__name__}: grouped binding must contain direct source/value items")
    if not items or any(type(item) not in (LiteralDependency, UpstreamDependency) for item in items):
        raise ValueError(f"{fn.__name__}: grouped binding must contain direct source/value items")
    return items
