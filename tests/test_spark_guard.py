"""Pure construction-time G3 safety boundary; no Spark profile import required."""

from collections.abc import Callable

import pytest

from sdax_hamilton._hamilton_spark import reject_unsafe_spark_cones
from sdax_hamilton._model import InputSpec, NodeSpec
from sdax_hamilton.declarations import Policy


def _node(
    name: str,
    fn: Callable[..., object],
    *,
    inputs: dict[str, InputSpec] | None = None,
    ownership_required: bool = False,
    release: Callable[..., object] | None = None,
    policy: Policy = Policy(),
    release_policy: Policy = Policy(),
    borrow_from: frozenset[str] = frozenset(),
) -> NodeSpec:
    return NodeSpec(
        name,
        fn,
        object,
        {} if inputs is None else inputs,
        ownership_required=ownership_required,
        release=release,
        policy=policy,
        release_policy=release_policy,
        borrow_from=borrow_from,
    )


def test_spark_guard_allows_plain_upstream_transforms_and_external_dataframe():
    def plain() -> object:
        raise AssertionError("construction must not call a graph callback")

    nodes = {
        "plain": _node("plain", plain),
        "spark.generated": _node(
            "spark.generated", plain, inputs={"plain": InputSpec(object), "frame": InputSpec(object)}
        ),
    }

    assert reject_unsafe_spark_cones(nodes, {"spark.generated"}) == {
        "plain",
        "spark.generated",
    }


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("ownership_required", True, "owned acquisition"),
        ("release", lambda _: None, "shutdown callback"),
        ("borrow_from", frozenset({"owner"}), "borrowed value"),
        ("policy", Policy(timeout=1.0), "nondefault policy"),
        ("release_policy", Policy(timeout=1.0), "nondefault policy"),
    ),
)
def test_spark_guard_rejects_unsafe_ancestor_before_any_callback(field, value, message):
    calls: list[str] = []

    def unsafe() -> object:
        calls.append("called")
        return object()

    unsafe_kwargs = {field: value}
    nodes = {
        "unsafe": _node("unsafe", unsafe, **unsafe_kwargs),
        "spark.generated": _node(
            "spark.generated", unsafe, inputs={"unsafe": InputSpec(object)}
        ),
    }

    with pytest.raises(ValueError, match=message):
        reject_unsafe_spark_cones(nodes, {"spark.generated"})
    assert calls == []


def test_spark_guard_checks_the_complete_cone_before_configuration_or_override_selection():
    def callback() -> object:
        raise AssertionError("construction must not call a graph callback")

    nodes = {
        "acquire": _node("acquire", callback, ownership_required=True),
        "spark.generated": _node(
            "spark.generated", callback, inputs={"acquire": InputSpec(object)}
        ),
    }

    with pytest.raises(ValueError, match="owned acquisition"):
        reject_unsafe_spark_cones(nodes, {"spark.generated"})


def test_spark_guard_rejects_unknown_generated_node_identity():
    with pytest.raises(AssertionError, match="Unknown captured Spark nodes"):
        reject_unsafe_spark_cones({}, {"spark.generated"})
