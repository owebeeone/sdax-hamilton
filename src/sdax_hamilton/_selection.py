"""Select and validate an immutable execution shape before effects begin."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ._model import MISSING, NodeSpec
from ._types import accepts, compatible, validate_type


def names(values: Iterable[str], label: str, *, nonempty: bool = False) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{label} must be a collection of node names, not a string")
    result = tuple(values)
    if any(not isinstance(name, str) or not name for name in result):
        raise ValueError(f"{label} requires nonempty node names")
    if nonempty and not result:
        raise ValueError(f"{label} must not be empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{label} contains duplicate names")
    return result


@dataclass(frozen=True, slots=True)
class Selection:
    nodes: Mapping[str, NodeSpec]
    outputs: tuple[str, ...]
    config: Mapping[str, Any]
    external: Mapping[str, tuple[Any, ...]]
    overrides: frozenset[str]
    active: frozenset[str]


def select(
    nodes: Mapping[str, NodeSpec],
    final_vars: Iterable[str],
    *,
    config: Mapping[str, Any] | None = None,
    optional_inputs: Iterable[str] = (),
    override_nodes: Iterable[str] = (),
) -> Selection:
    nodes = MappingProxyType(dict(nodes))
    config = MappingProxyType(dict(config or {}))
    outputs = names(final_vars, "final_vars", nonempty=True)
    optional = frozenset(names(optional_inputs, "optional_inputs"))
    overrides = frozenset(names(override_nodes, "override_nodes"))
    if overrides - nodes.keys():
        raise ValueError(f"Unknown override nodes: {sorted(overrides - nodes.keys())}")
    if overrides & config.keys():
        raise ValueError("Configuration and overrides must be disjoint")
    selected: set[str] = set()
    state: dict[str, int] = {}
    required: set[str] = set()
    contracts: dict[str, list[Any]] = {}
    # Iterative traversal keeps deep user graphs off the Python call stack.
    stack = [(name, False) for name in reversed(outputs)]
    while stack:
        name, exiting = stack.pop()
        if exiting:
            state[name] = 2
            continue
        if state.get(name) == 1:
            raise ValueError(f"Dependency cycle at {name!r}")
        if state.get(name) == 2:
            continue
        if name not in nodes:
            raise ValueError(f"Unknown selected node: {name!r}")
        spec = nodes[name]
        validate_type(spec.output_type)
        if spec.ownership_required and spec.release is None:
            raise ValueError(f"Selected acquisition expansion lacks shutdown: {name}")
        if spec.release is not None and (name in config or name in overrides):
            raise ValueError(f"Cannot replace owned acquisition: {name}")
        if spec.release is not None and spec.policy.retries:
            raise ValueError(f"Acquisition retries require attempt cleanup: {name}")
        selected.add(name)
        state[name] = 1
        stack.append((name, True))
        if name in config:
            if not accepts(config[name], spec.output_type):
                raise TypeError(f"Invalid config replacement: {name}")
            continue
        if name in overrides:
            continue
        dependencies = []
        for dependency, binding in spec.inputs.items():
            validate_type(binding.typ)
            requirements = binding.effective_requirements
            for requirement in requirements:
                validate_type(requirement)
            if binding.default is not MISSING and not all(
                accepts(binding.default, requirement) for requirement in requirements
            ):
                raise TypeError(f"Invalid default for {name}.{dependency}")
            if dependency in nodes:
                if not all(
                    compatible(nodes[dependency].output_type, requirement)
                    for requirement in requirements
                ):
                    raise TypeError(f"Incompatible edge: {dependency} -> {name}")
                dependencies.append((dependency, False))
            elif dependency in config:
                if not all(accepts(config[dependency], requirement) for requirement in requirements):
                    raise TypeError(f"Invalid config input {dependency!r} for {name}")
            else:
                contracts.setdefault(dependency, []).extend(requirements)
                if binding.default is MISSING or dependency in optional:
                    required.add(dependency)
        stack.extend(reversed(dependencies))
    if overrides - selected:
        raise ValueError(f"Unused override declaration: {sorted(overrides - selected)}")
    if optional - required:
        raise ValueError(f"Unused optional input declaration: {sorted(optional - required)}")
    for name in selected - config.keys() - overrides:
        for dependency, binding in nodes[name].inputs.items():
            if dependency in nodes and dependency in config and not all(
                accepts(config[dependency], requirement)
                for requirement in binding.effective_requirements
            ):
                raise TypeError(f"Invalid config replacement: {dependency}")
    return Selection(
        nodes,
        outputs,
        config,
        MappingProxyType({name: tuple(contracts[name]) for name in sorted(required)}),
        overrides,
        frozenset(selected - config.keys() - overrides),
    )
