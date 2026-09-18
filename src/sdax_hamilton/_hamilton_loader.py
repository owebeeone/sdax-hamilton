"""Pinned correction for Hamilton's generated ``load_from`` node annotations.

Hamilton 1.90.0's generated loader callable returns ``(data, metadata)`` but
declares its raw node as ``tuple[dict[str, Any], data_type]``. This module only
normalizes a pair from a compiler invocation already known to have admitted a
``LoadFromDecorator``. It does not select adapters, execute loaders, or inspect
the process-wide Hamilton registry.
"""

from collections.abc import Iterable
from types import GenericAlias
from typing import Any

from hamilton import node

_DATA_LOADER_TAG = "hamilton.data_loader"
_HAS_METADATA_TAG = "hamilton.data_loader.has_metadata"
_LOADER_NODE_TAG = "hamilton.data_loader.node"
_LOADER_CLASS_TAG = "hamilton.data_loader.classname"
_METADATA_TYPE = dict[str, Any]


def _tuple_type(first: Any, second: Any) -> Any:
    """Construct the runtime generic alias Hamilton's node model stores."""
    return GenericAlias(tuple, (first, second))


def _loader_identity(entry: node.Node, has_metadata: bool) -> tuple[str, str] | None:
    """Return the generated pair identity only for a complete loader tag shape."""
    tags = entry.tags
    if tags.get(_DATA_LOADER_TAG) is not True or tags.get(_HAS_METADATA_TAG) is not has_metadata:
        return None
    loader_node = tags.get(_LOADER_NODE_TAG)
    loader_class = tags.get(_LOADER_CLASS_TAG)
    if not isinstance(loader_node, str) or not loader_node:
        return None
    if not isinstance(loader_class, str) or not loader_class:
        return None
    return loader_node, loader_class


def correct_load_from_annotations(
    entries: Iterable[node.Node], *, load_from_admitted: bool
) -> tuple[node.Node, ...]:
    """Return copied 1.90.0 ``load_from`` pairs with their raw tuple typed correctly.

    The caller supplies ``load_from_admitted`` only from its existing per-function
    admission decision and only after the enclosing Hamilton compatibility version
    check. Tagged nodes alone never activate this correction. A known admitted
    invocation whose generated raw/projection shape differs from Hamilton 1.90.0
    fails closed instead of guessing from node names or weakening type checks.
    """
    original = tuple(entries)
    if not load_from_admitted:
        return original

    raw_entries = [entry for entry in original if _loader_identity(entry, True) is not None]
    if not raw_entries:
        raise RuntimeError("Admitted load_from produced no generated raw loader node")

    replacements: dict[int, node.Node] = {}
    for raw in raw_entries:
        identity = _loader_identity(raw, True)
        assert identity is not None
        projections = [
            entry
            for entry in original
            if _loader_identity(entry, False) == identity and raw.name in entry.input_types
        ]
        if len(projections) != 1:
            raise RuntimeError("Admitted load_from generated an ambiguous loader projection")
        projection = projections[0]
        raw_input_type, dependency_kind = projection.input_types[raw.name]
        expected_type = _tuple_type(projection.type, _METADATA_TYPE)
        reversed_type = _tuple_type(_METADATA_TYPE, projection.type)
        if raw.type not in (expected_type, reversed_type) or raw_input_type != raw.type:
            raise RuntimeError("Admitted load_from generated an unexpected raw loader annotation")

        if raw.type == expected_type:
            continue

        replacements[id(raw)] = raw.copy_with(typ=expected_type)
        corrected_inputs = projection.input_types.copy()
        corrected_inputs[raw.name] = (expected_type, dependency_kind)
        replacements[id(projection)] = projection.copy_with(input_types=corrected_inputs)

    return tuple(replacements.get(id(entry), entry) for entry in original)
