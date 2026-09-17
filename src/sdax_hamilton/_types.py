"""Deliberately bounded checks for declared bindings, not a Python type prover."""

import types
from typing import Any, Literal, Tuple, Union, get_args, get_origin


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


def validate_type(typ: Any) -> None:
    """Reject unsupported annotation forms before graph execution."""
    if typ is Any or typ is None or typ is type(None):
        return
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        for arg in args:
            validate_type(arg)
        return
    if origin is Literal:
        if not args or any(type(arg) not in (str, int, bool, bytes, type(None)) for arg in args):
            raise TypeError(f"Unsupported literal annotation: {typ!r}")
        return
    if origin in (list, dict, tuple, set, frozenset):
        if origin in (list, set, frozenset) and len(args) not in (0, 1):
            raise TypeError(f"Invalid container annotation: {typ!r}")
        if origin is dict and len(args) not in (0, 2):
            raise TypeError(f"Invalid dictionary annotation: {typ!r}")
        if Ellipsis in args and not (origin is tuple and len(args) == 2 and args[1] is Ellipsis):
            raise TypeError(f"Invalid variadic annotation: {typ!r}")
        for arg in args:
            if arg is not Ellipsis:
                validate_type(arg)
        return
    if isinstance(typ, type) and not getattr(typ, "_is_protocol", False):
        # TypedDict and similar pseudo-classes do not support isinstance.
        try:
            isinstance(None, typ)
        except TypeError as exc:
            raise TypeError(f"Unsupported runtime annotation: {typ!r}") from exc
        return
    raise TypeError(f"Unsupported annotation: {typ!r}")


def accepts(value: object, typ: Any) -> bool:
    """Check supported runtime values, including all container elements."""
    validate_type(typ)
    if typ is Any:
        return True
    if typ is None:
        typ = type(None)
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        return any(accepts(value, arg) for arg in args)
    if origin is Literal:
        return any(type(value) is type(arg) and value == arg for arg in args)
    if origin in (dict, list, set, frozenset, tuple):
        if not isinstance(value, origin):
            return False
        if not args:
            return len(value) == 0 if origin is tuple and typ is not Tuple else True  # type: ignore[arg-type]
        if origin is dict:
            return all(accepts(k, args[0]) and accepts(v, args[1]) for k, v in value.items())  # type: ignore[attr-defined]
        if origin in (list, set, frozenset):
            return all(accepts(item, args[0]) for item in value)  # type: ignore[union-attr]
        if len(args) == 2 and args[1] is Ellipsis:
            return all(accepts(item, args[0]) for item in value)  # type: ignore[union-attr]
        return len(value) == len(args) and all(  # type: ignore[arg-type]
            accepts(item, arg)
            for item, arg in zip(value, args)  # type: ignore[arg-type]
        )
    return isinstance(value, typ)


def compatible(produced: Any, required: Any) -> bool:
    """Conservative edge assignability; Any is an explicit unchecked escape."""
    validate_type(produced)
    validate_type(required)
    produced = type(None) if produced is None else produced
    required = type(None) if required is None else required
    if produced is Any or required is Any or produced == required:
        return True
    po, ro = get_origin(produced), get_origin(required)
    if po in (Union, types.UnionType):
        return all(compatible(arg, required) for arg in get_args(produced))
    if ro in (Union, types.UnionType):
        return any(compatible(produced, arg) for arg in get_args(required))
    if po is Literal:
        return all(accepts(arg, required) for arg in get_args(produced))
    if po and isinstance(required, type):
        return isinstance(po, type) and issubclass(po, required)
    if ro is tuple and required is not Tuple and not get_args(required):
        # Empty tuple annotations and bare typing.Tuple both expose no args,
        # but only the latter accepts arbitrary tuple contents.
        return po is tuple and produced is not Tuple and not get_args(produced)
    if po is ro and po in (list, dict, tuple, set, frozenset):
        return not get_args(required) or get_args(produced) == get_args(required)
    if isinstance(produced, type) and isinstance(required, type):
        return issubclass(produced, required)
    return False
