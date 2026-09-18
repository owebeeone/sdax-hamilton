"""Immutable frontend graph representation, independent of Hamilton internals."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from ._types import MISSING as MISSING
from .declarations import Policy


@dataclass(frozen=True, slots=True)
class InputSpec:
    typ: Any
    default: object = MISSING
    requirements: tuple[Any, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "requirements", tuple(self.requirements))

    @property
    def effective_requirements(self) -> tuple[Any, ...]:
        return self.requirements or (self.typ,)


@dataclass(frozen=True, slots=True)
class NodeSpec:
    name: str
    fn: Callable[..., Any]
    output_type: Any
    inputs: Mapping[str, InputSpec]
    tags: Mapping[str, Any] = field(default_factory=dict)
    policy: Policy = Policy()
    release: Callable[..., Any] | None = None
    release_policy: Policy = Policy()
    origin: str = ""
    ownership_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        object.__setattr__(
            self,
            "tags",
            MappingProxyType(
                {key: list(value) if isinstance(value, list) else value for key, value in self.tags.items()}
            ),
        )
