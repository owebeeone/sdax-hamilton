"""The explicit declaration type subset, independent of Hamilton internals."""

from collections.abc import Callable, Iterable, Mapping
from typing import Annotated, Any, Dict, List, Literal, Protocol, Set, Tuple, TypeVar

import pytest

from sdax_hamilton import Driver
from sdax_hamilton._types import accepts, compatible, validate_type


class Parent:
    pass


class Child(Parent):
    pass


class Shape(Protocol):
    def draw(self) -> None: ...


@pytest.mark.parametrize(
    "annotation, good, bad",
    [
        (int, 3, "3"),
        (str, "hello", 1),
        (float, 1.0, "1.0"),
        (bool, True, 1),
        (None, None, 0),
        (type(None), None, ""),
        (Parent, Child(), object()),
        (int | str, "x", None),
        (int | None, None, "x"),
        (Literal["red", "blue"], "red", "green"),
        (Literal[1], 1, True),
        (Literal[True], True, 1),
        (Literal[None], None, 0),
        (list[int], [1, 2], [1, "2"]),
        (set[str], {"x"}, {"x", 1}),
        (dict[str, list[int]], {"x": [1]}, {"x": ["bad"]}),
        (tuple[int, str], (1, "x"), (1, 2)),
        (tuple[int, str], (1, "x"), (1, "x", 2)),
        (tuple[int, ...], (1, 2), (1, "x")),
        (tuple[()], (), (1,)),
    ],
)
def test_runtime_type_subset(annotation, good, bad):
    validate_type(annotation)
    assert accepts(good, annotation)
    assert not accepts(bad, annotation)


@pytest.mark.parametrize("value", [None, object(), 1, ["anything"]])
def test_any_accepts_values(value):
    assert accepts(value, Any)


@pytest.mark.parametrize(
    "annotation, good, bad",
    [
        (list, [1], (1,)),
        (List, [1], (1,)),
        (dict, {"x": 1}, [("x", 1)]),
        (Dict, {"x": 1}, [("x", 1)]),
        (tuple, (1, "x"), [1, "x"]),
        (Tuple, (1, "x"), [1, "x"]),
        (set, {1}, [1]),
        (Set, {1}, [1]),
    ],
)
def test_bare_container_annotations_do_not_index_missing_type_arguments(annotation, good, bad):
    validate_type(annotation)
    assert accepts(good, annotation)
    assert not accepts(bad, annotation)


@pytest.mark.parametrize(
    "produced, required, expected",
    [
        (Child, Parent, True),
        (Parent, Child, False),
        (None, type(None), True),
        (int, str, False),
        (Any, int, True),
        (int, Any, True),
        (int, int | str, True),
        (int | str, int, False),
        (int | str, int | str | None, True),
        (Literal["red"], str, True),
        (Literal[1], int, True),
        (Literal["red"], Literal["red", "blue"], True),
        (Literal["red", "blue"], Literal["red"], False),
        (Literal[1], Literal[True], False),
        (list[int], list[int], True),
        (list[str], list[int], False),
        (dict[str, int], dict[str, int], True),
        (tuple[int, str], tuple[int, str], True),
        (tuple[int, str], tuple[str, int], False),
    ],
)
def test_declared_edge_compatibility(produced, required, expected):
    assert compatible(produced, required) is expected


@pytest.mark.parametrize(
    "annotation",
    [
        TypeVar("T"),
        Shape,
        Annotated[int, "metadata"],
        Callable[[int], str],
        Iterable[int],
        Mapping[str, int],
        list[TypeVar("Item")],
        Literal[1.5],
        "UnresolvedForwardReference",
    ],
)
def test_unsupported_annotations_fail_explicitly(annotation):
    with pytest.raises(TypeError):
        validate_type(annotation)


@pytest.mark.parametrize(
    "source",
    [
        """
def thing() -> str:
    return 'x'
def result(thing: int) -> int:
    return thing
""",
        """
def result(count: int = 'bad') -> int:
    return count
""",
    ],
)
def test_invalid_edge_and_default_rejected_before_execution(module_factory, source):
    with pytest.raises((TypeError, ValueError)):
        Driver(module_factory(source)).prepare(["result"])


@pytest.mark.asyncio
async def test_heterogeneous_tuple_input_checked_before_callback(module_factory):
    calls = []
    mod = module_factory(
        """
def result(pair: tuple[int, str]) -> str:
    calls.append('ran')
    return pair[1]
""",
        calls=calls,
    )
    plan = Driver(mod).prepare(["result"])
    assert await plan.execute(inputs={"pair": (1, "x")}) == {"result": "x"}
    with pytest.raises(TypeError):
        await plan.execute(inputs={"pair": (1, 2)})
    assert calls == ["ran"]
