"""Deliberately bounded checks for declared bindings, not a Python type prover."""

import types
from typing import (
    Any,
    Literal,
    NotRequired,
    Required,
    Tuple,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from typing_extensions import is_typeddict


class _Missing:
    def __repr__(self) -> str:
        return "MISSING"


MISSING = _Missing()


def _typed_dict_fields(typ: Any) -> tuple[tuple[str, Any, bool], ...]:
    """Resolve the finite runtime shape used by admitted ``extract_fields`` outputs."""
    try:
        hints = get_type_hints(typ, include_extras=True)
    except (NameError, TypeError) as exc:
        raise TypeError(f"Unsupported TypedDict annotation: {typ!r}") from exc
    raw_required: Any = getattr(typ, "__required_keys__", frozenset())
    raw_optional: Any = getattr(typ, "__optional_keys__", frozenset())
    if not isinstance(raw_required, (set, frozenset)) or not isinstance(
        raw_optional, (set, frozenset)
    ):
        raise TypeError(f"Unsupported TypedDict annotation: {typ!r}")
    required: set[Any] | frozenset[Any] = raw_required
    optional: set[Any] | frozenset[Any] = raw_optional
    fields = []
    for name, field_type in hints.items():
        if not isinstance(name, str):
            raise TypeError(f"Unsupported TypedDict annotation: {typ!r}")
        origin, args = get_origin(field_type), get_args(field_type)
        if origin in (Required, NotRequired):
            if len(args) != 1:
                raise TypeError(f"Unsupported TypedDict annotation: {typ!r}")
            fields.append((name, args[0], origin is Required))
        elif name in required:
            fields.append((name, field_type, True))
        elif name in optional:
            fields.append((name, field_type, False))
        else:
            fields.append((name, field_type, bool(getattr(typ, "__total__", True))))
    return tuple(fields)


def validate_type(typ: Any) -> None:
    """Reject unsupported annotation forms before graph execution."""
    _validate_type(typ, set())


def _validate_type(typ: Any, active_typed_dicts: set[Any]) -> None:
    if typ is Any or typ is None or typ is type(None):
        return
    if is_typeddict(typ):
        if typ in active_typed_dicts:
            return
        active_typed_dicts.add(typ)
        try:
            for _, field_type, _ in _typed_dict_fields(typ):
                _validate_type(field_type, active_typed_dicts)
        finally:
            active_typed_dicts.remove(typ)
        return
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        for arg in args:
            _validate_type(arg, active_typed_dicts)
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
                _validate_type(arg, active_typed_dicts)
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
    return _accepts(value, typ, set())


def _accepts(value: object, typ: Any, active_values: set[tuple[int, Any]]) -> bool:
    if typ is Any:
        return True
    if typ is None:
        typ = type(None)
    if is_typeddict(typ):
        if not isinstance(value, dict):
            return False
        marker = (id(value), typ)
        if marker in active_values:
            return True
        active_values.add(marker)
        try:
            return all(
                (name in value and _accepts(value[name], field_type, active_values))
                if required
                else (name not in value or _accepts(value[name], field_type, active_values))
                for name, field_type, required in _typed_dict_fields(typ)
            )
        finally:
            active_values.remove(marker)
    origin, args = get_origin(typ), get_args(typ)
    if origin in (Union, types.UnionType):
        return any(_accepts(value, arg, active_values) for arg in args)
    if origin is Literal:
        return any(type(value) is type(arg) and value == arg for arg in args)
    if origin in (dict, list, set, frozenset, tuple):
        if not isinstance(value, origin):
            return False
        if not args:
            return len(value) == 0 if origin is tuple and typ is not Tuple else True  # type: ignore[arg-type]
        if origin is dict:
            return all(
                _accepts(k, args[0], active_values) and _accepts(v, args[1], active_values)
                for k, v in value.items()
            )  # type: ignore[attr-defined]
        if origin in (list, set, frozenset):
            return all(_accepts(item, args[0], active_values) for item in value)  # type: ignore[union-attr]
        if len(args) == 2 and args[1] is Ellipsis:
            return all(_accepts(item, args[0], active_values) for item in value)  # type: ignore[union-attr]
        return len(value) == len(args) and all(  # type: ignore[arg-type]
            _accepts(item, arg, active_values)
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
    if is_typeddict(produced):
        # A TypedDict is a runtime dict, but proving structural compatibility
        # with another TypedDict or a parameterized dictionary is out of scope.
        return required in (dict, object)
    if is_typeddict(required):
        return False
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
