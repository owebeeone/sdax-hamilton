"""Construction-time safety checks for an admitted caller-owned Spark plan."""

from collections.abc import Collection, Mapping

from ._model import NodeSpec
from .declarations import Policy


def reject_spark_io(name: str, tags: Mapping[str, object]) -> None:
    """Known I/O effects cannot participate in the lazy, caller-owned profile."""
    if tags.get("hamilton.data_loader") is True or tags.get("hamilton.data_saver") is True:
        raise ValueError(f"{name}: Spark plans cannot compose Hamilton I/O decorators")


def reject_unsafe_spark_cones(
    nodes: Mapping[str, NodeSpec], spark_nodes: Collection[str]
) -> frozenset[str]:
    """Reject upstream lifecycle state and I/O connected to exact Spark nodes.

    ``spark_nodes`` is supplied only by the exact copied Spark decorator hook
    during graph construction. The check intentionally runs on the complete
    captured graph before selection, configuration replacement, or overrides;
    callers therefore cannot hide an owned or policy-bearing ancestor by
    replacing it in a prepared plan. Inputs absent from ``nodes`` remain
    caller-owned external values.
    """
    selected = frozenset(spark_nodes)
    if any(not isinstance(name, str) or not name for name in selected):
        raise ValueError("Spark generated nodes require nonempty names")
    unknown = selected - nodes.keys()
    if unknown:
        raise AssertionError(f"Unknown captured Spark nodes: {sorted(unknown)}")

    cone: set[str] = set()
    pending = list(selected)
    while pending:
        name = pending.pop()
        if name in cone:
            continue
        cone.add(name)
        spec = nodes[name]
        reject_spark_io(name, spec.tags)
        if spec.ownership_required:
            raise ValueError(f"{name}: Spark plan cannot include an owned acquisition")
        if spec.release is not None:
            raise ValueError(f"{name}: Spark plan cannot include a shutdown callback")
        if spec.borrow_from:
            raise ValueError(f"{name}: Spark plan cannot include a borrowed value")
        if spec.policy != Policy() or spec.release_policy != Policy():
            raise ValueError(f"{name}: Spark plan cannot include a nondefault policy")
        pending.extend(dependency for dependency in spec.inputs if dependency in nodes)

    # A saver can consume the lazy result through ordinary forwarding nodes.
    # Check descendants too, without rejecting independent I/O branches sharing
    # an ordinary input with the Spark chain.
    dependents: dict[str, list[str]] = {}
    for name, spec in nodes.items():
        for dependency in spec.inputs:
            dependents.setdefault(dependency, []).append(name)
    descendants: set[str] = set()
    pending = list(selected)
    while pending:
        name = pending.pop()
        if name in descendants:
            continue
        descendants.add(name)
        reject_spark_io(name, nodes[name].tags)
        pending.extend(dependents.get(name, ()))
    return frozenset(cone)
