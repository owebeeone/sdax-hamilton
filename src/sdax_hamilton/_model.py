"""Immutable frontend graph representation, independent of Hamilton internals."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from ._types import MISSING as MISSING
from .declarations import Policy


class GeneratedRole(Enum):
    """Generated value roles with concrete selection or ownership consumers."""

    VALUE = "value"
    PROJECTION = "projection"
    VALIDATION_RAW = "validation-raw"
    VALIDATION_EVIDENCE = "validation-evidence"
    VALIDATION_GATE = "validation-gate"


@dataclass(frozen=True, slots=True)
class InputSpec:
    typ: Any
    default: object = MISSING


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
    role: GeneratedRole = GeneratedRole.VALUE
    borrow_from: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "inputs", MappingProxyType(dict(self.inputs)))
        if any(not isinstance(name, str) or not name for name in self.borrow_from):
            raise ValueError("borrow_from requires nonempty node names")
        object.__setattr__(self, "borrow_from", frozenset(self.borrow_from))
        object.__setattr__(
            self,
            "tags",
            MappingProxyType(
                {key: list(value) if isinstance(value, list) else value for key, value in self.tags.items()}
            ),
        )
