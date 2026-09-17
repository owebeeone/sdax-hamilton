"""Signature-preserving policy declarations and honest acquisition state."""

import asyncio
import math
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, Generic, ParamSpec, TypeVar, cast

from sdax import RetryableException

from ._types import MISSING, accepts

P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
Target = str | tuple[str, ...] | None
DEFAULT_RETRYABLE = (TimeoutError, ConnectionError, RetryableException)


@dataclass(frozen=True, slots=True)
class Policy:
    timeout: float | None = None
    retries: int = 0
    retryable_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE
    initial_delay: float = 1.0
    backoff_factor: float = 2.0

    def __post_init__(self) -> None:
        if type(self.retries) is not int or self.retries < 0:
            raise ValueError("retries must be a nonnegative integer")
        for name in ("timeout", "initial_delay", "backoff_factor"):
            value = getattr(self, name)
            if name == "timeout" and value is None:
                continue
            if type(value) not in (int, float) or not math.isfinite(value):
                raise ValueError(f"{name} must be a finite number")
            if value < 0 or (name != "initial_delay" and value == 0):
                raise ValueError(f"Invalid {name}: {value}")
        if not isinstance(self.retryable_exceptions, tuple) or not self.retryable_exceptions:
            raise ValueError("retryable_exceptions must be a nonempty tuple of exception classes")
        for exc in self.retryable_exceptions:
            if not isinstance(exc, type) or not issubclass(exc, BaseException):
                raise ValueError("retryable_exceptions must contain exception classes")
            if any(
                issubclass(fatal, exc)
                for fatal in (asyncio.CancelledError, KeyboardInterrupt, SystemExit)
            ):
                raise ValueError(
                    "External cancellation and process termination cannot be retryable"
                )

    def settings(self) -> dict[str, Any]:
        return {
            name: getattr(self, name)
            for name in (
                "timeout",
                "retries",
                "retryable_exceptions",
                "initial_delay",
                "backoff_factor",
            )
        }


def _target(value: str | Collection[str] | None) -> Target:
    if value is None:
        return None
    if isinstance(value, str):
        if not value:
            raise ValueError("target_ must not be empty")
        return value
    if not isinstance(value, Collection) or isinstance(value, (bytes, dict)):
        raise TypeError("target_ must be a node name or collection of names")
    names = tuple(value)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError("target_ requires nonempty node names")
    if len(set(names)) != len(names):
        raise ValueError("target_ contains duplicate names")
    return names


def execution(
    *,
    target_: str | Collection[str] | None = None,
    timeout: float | None = None,
    retries: int = 0,
    retryable_exceptions: tuple[type[BaseException], ...] | None = None,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Attach per-attempt policy; direct Python calls remain ordinary calls."""
    policy = Policy(
        timeout,
        retries,
        DEFAULT_RETRYABLE if retryable_exceptions is None else retryable_exceptions,
        initial_delay,
        backoff_factor,
    )
    target = _target(target_)

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        if hasattr(fn, "__sdax_execution__") or hasattr(fn, "__sdax_shutdown__"):
            raise ValueError("Conflicting execution/shutdown declaration")
        setattr(fn, "__sdax_execution__", (policy, target))
        return fn

    return decorate


def shutdown(
    *,
    of: Callable[..., Any],
    target_: str | Collection[str] | None = None,
    timeout: float | None = None,
    retries: int = 0,
    retryable_exceptions: tuple[type[BaseException], ...] | None = None,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Associate a release with acquisition origin(s); no global registry."""
    if not callable(of):
        raise TypeError("shutdown of= must refer to an acquisition function")
    policy = Policy(
        timeout,
        retries,
        DEFAULT_RETRYABLE if retryable_exceptions is None else retryable_exceptions,
        initial_delay,
        backoff_factor,
    )
    target = _target(target_)

    def decorate(fn: Callable[P, R]) -> Callable[P, R]:
        if hasattr(fn, "__sdax_shutdown__") or hasattr(fn, "__sdax_execution__"):
            raise ValueError("Conflicting execution/shutdown declaration")
        setattr(fn, "__sdax_shutdown__", (of, target, policy))
        return fn

    return decorate


@dataclass(frozen=True, slots=True)
class Acquisition(Generic[T]):
    """Per-invocation raw ownership record; value checks its annotation on access."""

    _raw: object = MISSING
    _typ: Any = Any

    @property
    def has_value(self) -> bool:
        return self._raw is not MISSING

    @property
    def raw_value(self) -> object:
        if not self.has_value:
            raise ValueError("Acquisition did not publish a value")
        return self._raw

    @property
    def is_valid(self) -> bool:
        return self.has_value and accepts(self._raw, self._typ)

    @property
    def value(self) -> T:
        if not self.is_valid:
            raise TypeError("Acquisition has no validated typed value; inspect raw_value")
        return cast(T, self._raw)
