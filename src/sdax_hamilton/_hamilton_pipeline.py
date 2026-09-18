"""Private correction for Hamilton 1.90.0 async output-pipeline expansion.

This module operates only on modifier instances already copied by
``hamilton_compat._copy_function``. It does not admit pipeline decorators to the
frontend; phase C must call it after separately qualifying the supported forms.
"""

import inspect
from copy import copy
from importlib import metadata
from types import FunctionType, MethodType
from typing import Any, Callable

import hamilton
from hamilton.function_modifiers.configuration import ConfigResolver
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.function_modifiers.macros import Applicable, does, pipe, pipe_input, pipe_output

_SUPPORTED_HAMILTON_VERSION = "1.90.0"
_CORRECTION_MARKER = "__sdax_hamilton_async_output_pipeline_corrected__"
_PIPE_MODIFIERS = (pipe_input, pipe, pipe_output)
_SELECTOR_FACTORIES = (
    (ConfigResolver.when().resolves.__code__, ("key_value_pairs",), ConfigResolver.when),
    (ConfigResolver.when_not().resolves.__code__, ("key_value_pairs",), ConfigResolver.when_not),
    (ConfigResolver.when_in().resolves.__code__, ("key_value_group_pairs",), ConfigResolver.when_in),
    (
        ConfigResolver.when_not_in().resolves.__code__,
        ("key_value_group_pairs",),
        ConfigResolver.when_not_in,
    ),
)


def _check_hamilton_version() -> None:
    """Fail closed outside the pinned upstream implementation."""
    try:
        installed = metadata.version("apache-hamilton")
    except metadata.PackageNotFoundError as exc:
        raise RuntimeError("async output-pipeline correction requires apache-hamilton==1.90.0") from exc
    source_version = getattr(hamilton, "__version__", ())
    imported = (
        source_version if isinstance(source_version, str) else ".".join(map(str, source_version))
    )
    if installed != _SUPPORTED_HAMILTON_VERSION or imported != _SUPPORTED_HAMILTON_VERSION:
        raise RuntimeError(
            "Unsupported Hamilton version for async output-pipeline correction: "
            f"distribution={installed}, imported={imported}; "
            "requires apache-hamilton==1.90.0"
        )


def _synchronous_expansion_context(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Supply only the name context used by the pinned upstream transformer.

    The actual producer remains on the input ``Node`` and retains its coroutine
    callable. The proxy is never emitted as a Hamilton node.
    """

    def context(*args: Any, **kwargs: Any) -> Any:
        return fn(*args, **kwargs)

    context.__name__ = fn.__name__
    context.__qualname__ = fn.__qualname__
    return context


def _corrected_transform_node(original: Callable[..., Any]) -> Callable[..., Any]:
    """Delegate pinned ``pipe_output`` expansion with a synchronous name context."""

    def transform_node(self: pipe_output, node_: Any, config: dict[str, Any], fn: Callable[..., Any]):
        if inspect.iscoroutinefunction(fn):
            return original(node_, config, _synchronous_expansion_context(fn))
        return original(node_, config, fn)

    return transform_node


def correct_copied_async_output_pipelines(fn: Callable[..., Any]) -> None:
    """Correct exact copied ``pipe_output`` modifiers for Hamilton 1.90.0.

    Calling this function repeatedly is idempotent. The caller must pass an
    isolated declaration copy and retain the current frontend's separate
    decorator-admission checks.
    """

    _check_hamilton_version()
    if not inspect.iscoroutinefunction(fn):
        return
    for modifier in getattr(fn, "transform", ()):
        if type(modifier) is not pipe_output or getattr(modifier, _CORRECTION_MARKER, False):
            continue
        original = modifier.transform_node
        modifier.transform_node = MethodType(_corrected_transform_node(original), modifier)
        setattr(modifier, _CORRECTION_MARKER, True)


def _copy_metadata_container(value: Any) -> Any:
    """Copy finite Hamilton metadata containers while keeping application values intact."""
    if type(value) is list:
        return list(value)
    if type(value) is tuple:
        return tuple(value)
    if type(value) is set:
        return set(value)
    if type(value) is frozenset:
        return frozenset(value)
    return value


def _copy_config_resolver(resolver: ConfigResolver) -> ConfigResolver:
    """Rebuild one known built-in step selector without retaining its closure mapping."""
    if type(resolver) is not ConfigResolver:
        raise ValueError("pipeline steps require a built-in Hamilton configuration selector")
    resolve = resolver.resolves
    if resolve.__closure__ is None or len(resolve.__closure__) != 1:
        raise ValueError("unsupported Hamilton pipeline configuration selector")
    for code, freevars, factory in _SELECTOR_FACTORIES:
        if resolve.__code__ is not code or resolve.__code__.co_freevars != freevars:
            continue
        (pairs,) = (cell.cell_contents for cell in resolve.__closure__)
        if type(pairs) is not dict or any(type(name) is not str for name in pairs):
            raise ValueError("unsupported Hamilton pipeline configuration selector")
        snapshot = {name: _copy_metadata_container(value) for name, value in pairs.items()}
        return factory(**snapshot)
    raise ValueError("unsupported Hamilton pipeline configuration selector")


def _copy_dependency(value: Any) -> Any:
    """Copy binding metadata while retaining literal application values by identity."""
    if type(value) is LiteralDependency or type(value) is UpstreamDependency:
        return copy(value)
    return value


def _copy_applicable(
    applicable: Applicable, copy_function: Callable[[FunctionType], FunctionType]
) -> Applicable:
    """Snapshot one exact pipeline declaration without traversing helper decorators."""
    if type(applicable) is not Applicable:
        raise ValueError("pipeline steps require Hamilton Applicable declarations")
    snapshot = copy(applicable)
    snapshot.args = tuple(_copy_dependency(value) for value in applicable.args)
    snapshot.kwargs = {
        name: _copy_dependency(value) for name, value in applicable.kwargs.items()
    }
    snapshot.resolvers = [_copy_config_resolver(resolver) for resolver in applicable.resolvers]
    snapshot.target = _copy_metadata_container(applicable.target)
    if type(applicable.fn) is FunctionType:
        snapshot.fn = copy_function(applicable.fn)
    # ``target_fn`` points at the import-time mutation target. It is not called
    # during this expansion, so retaining it does not retain executable helper
    # code or recursively admit that target's decorators.
    return snapshot


def _copy_plain_helper_function(fn: FunctionType) -> FunctionType:
    """Make a direct executable snapshot without traversing its decorator graph."""
    clone = FunctionType(fn.__code__, fn.__globals__, fn.__name__, fn.__defaults__, fn.__closure__)
    clone.__kwdefaults__ = dict(fn.__kwdefaults__ or {})
    clone.__annotations__ = dict(fn.__annotations__)
    clone.__dict__.update(fn.__dict__)
    clone.__module__ = fn.__module__
    clone.__qualname__ = fn.__qualname__
    clone.__doc__ = fn.__doc__
    return clone


def snapshot_copied_macro_bindings(
    fn: Callable[..., Any], copy_function: Callable[[FunctionType], FunctionType] | None = None
) -> None:
    """Snapshot exact macro binding containers on a declaration copy.

    This is a private construction helper. P2 owns provenance capture and C's
    later compiler admission; callers must pass a declaration already copied by
    ``hamilton_compat._copy_function``.
    """

    helper_memo: dict[int, FunctionType] = {}

    def copy_helper(value: FunctionType) -> FunctionType:
        if copy_function is not None:
            return copy_function(value)
        cached = helper_memo.get(id(value))
        if cached is None:
            cached = _copy_plain_helper_function(value)
            helper_memo[id(value)] = cached
        return cached

    for modifier in getattr(fn, "generate", ()):
        if type(modifier) is does:
            modifier.argument_mapping = dict(modifier.argument_mapping)
            if type(modifier.replacing_function) is FunctionType:
                modifier.replacing_function = copy_helper(modifier.replacing_function)
    for lifecycle in ("inject", "transform"):
        for modifier in getattr(fn, lifecycle, ()):
            if type(modifier) in _PIPE_MODIFIERS:
                modifier.transforms = tuple(
                    _copy_applicable(item, copy_helper) for item in modifier.transforms
                )
