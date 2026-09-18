"""Private correction for Hamilton 1.90.0 async output-pipeline expansion.

This module operates only on modifier instances already copied by
``hamilton_compat._copy_function``. It does not admit pipeline decorators to the
frontend; phase C must call it after separately qualifying the supported forms.
"""

import inspect
from importlib import metadata
from types import MethodType
from typing import Any, Callable

import hamilton
from hamilton.function_modifiers.macros import pipe_output

_SUPPORTED_HAMILTON_VERSION = "1.90.0"
_CORRECTION_MARKER = "__sdax_hamilton_async_output_pipeline_corrected__"


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
