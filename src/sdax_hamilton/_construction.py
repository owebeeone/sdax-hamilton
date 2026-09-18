"""Private failure transport for Hamilton's declaration construction boundary."""

from collections.abc import Callable
from types import TracebackType
from typing import Any

from hamilton.function_modifiers import base

_CONSTRUCTION_FAILURE_MESSAGE = "sdax_hamilton construction failure"
_METHODS = {
    "resolve": "resolve",
    "generate": "generate_nodes",
    "inject": "transform_dag",
    "expand": "transform_dag",
    "transform": "transform_dag",
    "decorate_nodes": "transform_dag",
    "dynamic": "resolve",
}


class _ConstructionFailure(BaseException):
    """Carry an ordinary user exception past Hamilton's construction logger."""

    def __init__(self, original: Exception, traceback: TracebackType | None):
        super().__init__(_CONSTRUCTION_FAILURE_MESSAGE)
        self.original = original
        self.traceback = traceback


def wrap_lifecycle(
    modifier: Any,
    *,
    wrap_result: Callable[[Any], Any] | None = None,
) -> Any:
    """Wrap one copied Hamilton modifier lifecycle without catching BaseException."""
    lifecycle = modifier.get_lifecycle_name()
    method_name = _METHODS[lifecycle]
    original = getattr(modifier, method_name)

    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            result = original(*args, **kwargs)
            return wrap_result(result) if wrap_result is not None else result
        except _ConstructionFailure:
            raise
        except Exception as exc:
            raise _ConstructionFailure(exc, exc.__traceback__) from None

    setattr(modifier, method_name, guarded)
    return modifier


def resolve_nodes(fn: Callable[..., Any], configuration: dict[str, Any]) -> Any:
    """Resolve nodes once and restore a wrapped user exception unchanged."""
    failure = None
    try:
        return base.resolve_nodes(fn, configuration)
    except _ConstructionFailure as caught:
        failure = caught
    assert failure is not None
    raise failure.original.with_traceback(failure.traceback)
