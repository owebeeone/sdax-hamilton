"""Identity-only discovery of declarations loaded by Hamilton subdag decorators."""

import sys
from dataclasses import dataclass
from types import FunctionType, ModuleType
from typing import Iterable

from hamilton.function_modifiers import base, parameterized_subdag, subdag
from hamilton.graph_utils import find_functions


@dataclass(frozen=True, slots=True)
class DeclarationSnapshot:
    """Ordered declaration identities; compilation owns every later transformation."""

    roots: tuple[FunctionType, ...]
    nested: tuple[FunctionType, ...]
    shutdowns: tuple[FunctionType, ...]


def _loaded_module(module: ModuleType) -> ModuleType:
    if sys.modules.get(module.__name__) is not module:
        raise ValueError(f"Declaration module {module.__name__!r} is not loaded")
    return module


def _defining_module(fn: FunctionType) -> ModuleType:
    module = sys.modules.get(fn.__module__)
    if not isinstance(module, ModuleType) or module.__dict__.get(fn.__name__) is not fn:
        raise ValueError(f"Declaration {fn.__qualname__!r} has an ambiguous defining module")
    return module


def _module_functions(module: ModuleType) -> tuple[FunctionType, ...]:
    _loaded_module(module)
    functions = tuple(fn for _, fn in find_functions(module))
    for fn in functions:
        _defining_module(fn)
    return functions


def _module_shutdowns(module: ModuleType) -> tuple[FunctionType, ...]:
    _loaded_module(module)
    shutdowns = tuple(fn for _, fn in find_functions(module) if hasattr(fn, "__sdax_shutdown__"))
    for release in shutdowns:
        _defining_module(release)
    return shutdowns


def _nested_functions(fn: FunctionType) -> tuple[FunctionType, ...]:
    nested: list[FunctionType] = []
    for modifier in getattr(fn, base.NodeCreator.get_lifecycle_name(), ()):
        if type(modifier) is subdag:
            sources = modifier.subdag_functions
        elif type(modifier) is parameterized_subdag:
            sources = modifier.load_from
        else:
            continue
        for source in sources:
            if isinstance(source, FunctionType):
                _defining_module(source)
                nested.append(source)
            elif isinstance(source, ModuleType):
                nested.extend(_module_functions(source))
            else:
                raise TypeError(f"Unsupported subdag declaration source: {source!r}")
    return tuple(nested)


def _matching_shutdowns(
    scopes: Iterable[ModuleType],
    owners: Iterable[FunctionType],
    *,
    root_scope_ids: frozenset[int] = frozenset(),
) -> tuple[FunctionType, ...]:
    owner_functions = tuple(owners)
    owner_ids = {id(owner) for owner in owner_functions}
    owner_names = {(owner.__module__, owner.__qualname__) for owner in owner_functions}
    shutdowns: list[FunctionType] = []
    shutdown_ids: set[int] = set()
    for scope in scopes:
        for release in _module_shutdowns(scope):
            owner = getattr(release, "__sdax_shutdown__")[0]
            if id(owner) not in owner_ids:
                if (owner.__module__, owner.__qualname__) in owner_names:
                    raise ValueError(f"Ambiguous shutdown owner for {release.__qualname__}")
                if id(scope) in root_scope_ids:
                    raise ValueError(f"{release.__name__}: owner not discovered in supplied modules")
                continue
            if id(release) in shutdown_ids:
                raise ValueError(f"Ambiguous duplicate shutdown declaration {release.__qualname__}")
            shutdown_ids.add(id(release))
            shutdowns.append(release)
    return tuple(shutdowns)


def discover_shutdowns_for(functions: Iterable[FunctionType]) -> tuple[FunctionType, ...]:
    """Return shutdowns for captured helper identities without expanding their modules."""
    helpers = tuple(dict.fromkeys(functions))
    if any(not isinstance(helper, FunctionType) for helper in helpers):
        raise TypeError("Shutdown discovery requires Python functions")
    scopes: list[ModuleType] = []
    scope_ids: set[int] = set()
    for helper in helpers:
        scope = _defining_module(helper)
        if id(scope) not in scope_ids:
            scope_ids.add(id(scope))
            scopes.append(scope)
    return _matching_shutdowns(scopes, helpers)


def discover_declarations(modules: Iterable[ModuleType]) -> DeclarationSnapshot:
    """Discover explicit subdag declarations without resolving Hamilton lifecycles."""
    root_modules = tuple(modules)
    if any(not isinstance(module, ModuleType) for module in root_modules):
        raise TypeError("Declaration discovery requires Python modules")
    roots = tuple(
        dict.fromkeys(
            fn
            for module in root_modules
            for fn in _module_functions(module)
            if not hasattr(fn, "__sdax_shutdown__")
        )
    )
    root_module_ids = {id(module) for module in root_modules}
    root_ids = {id(fn) for fn in roots}
    reached: list[FunctionType] = []
    nested: list[FunctionType] = []
    scopes: list[ModuleType] = []
    scope_ids: set[int] = set()
    seen: set[int] = set()
    active: set[int] = set()

    def remember_scope(module: ModuleType) -> None:
        if id(module) not in scope_ids:
            scope_ids.add(id(module))
            scopes.append(module)

    for module in root_modules:
        remember_scope(module)

    def visit(fn: FunctionType) -> None:
        module = _defining_module(fn)
        remember_scope(module)
        identity = id(fn)
        if identity in active:
            raise ValueError(f"Recursive subdag declaration cycle at {fn.__qualname__}")
        if identity in seen:
            return
        active.add(identity)
        reached.append(fn)
        if identity not in root_ids:
            nested.append(fn)
        for child in _nested_functions(fn):
            if hasattr(child, "__sdax_shutdown__"):
                remember_scope(_defining_module(child))
                continue
            visit(child)
        active.remove(identity)
        seen.add(identity)

    for root in roots:
        visit(root)

    shutdowns = _matching_shutdowns(
        scopes,
        reached,
        root_scope_ids=frozenset(root_module_ids),
    )
    return DeclarationSnapshot(tuple(roots), tuple(nested), shutdowns)
