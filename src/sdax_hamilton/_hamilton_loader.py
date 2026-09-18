"""Pinned correction for Hamilton's generated ``load_from`` node annotations.

Hamilton 1.90.0's generated loader callable returns ``(data, metadata)`` but
declares its raw node as ``tuple[dict[str, Any], data_type]``. This module only
normalizes a pair from a compiler invocation already known to have admitted a
``LoadFromDecorator``. It does not select adapters, execute loaders, or inspect
the process-wide Hamilton registry.
"""

from collections.abc import Iterable
from copy import copy
from types import GenericAlias, MethodType
from typing import Any, cast

from hamilton import node
from hamilton.function_modifiers.adapters import AdapterFactory, LoadFromDecorator, SaveToDecorator
from hamilton.function_modifiers.dependencies import LiteralDependency, UpstreamDependency
from hamilton.io.data_adapters import DataLoader, DataSaver

from ._types import accepts

_DATA_LOADER_TAG = "hamilton.data_loader"
_HAS_METADATA_TAG = "hamilton.data_loader.has_metadata"
_LOADER_NODE_TAG = "hamilton.data_loader.node"
_LOADER_CLASS_TAG = "hamilton.data_loader.classname"
_METADATA_TYPE = dict[str, Any]
_INSTALL_MARKER = object()
_FACTORY_DEFAULT_INDEX = 0
_RESOLVED_KWARGS_DEFAULT_INDEX = 2
_LOAD_DATA_DEFAULT_COUNT = 5
_SAVE_DATA_DEFAULT_COUNT = 4


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


def _validate_captured_adapter_literals(
    entry: node.Node,
    *,
    expected_default_count: int,
    adapter_type: type[DataLoader] | type[DataSaver],
    label: str,
) -> None:
    """Check one pinned generated adapter capture without another selection.

    The two admitted Hamilton 1.90.0 callables retain their already selected
    ``AdapterFactory`` and resolved literal mapping in fixed positional
    defaults. This deliberately reads only that generated shape: it never
    examines a registry or instantiates an adapter.
    """
    defaults = entry.callable.__defaults__
    if defaults is None or len(defaults) != expected_default_count:
        raise RuntimeError(f"Admitted {label} generated an unexpected adapter callable")
    factory = defaults[_FACTORY_DEFAULT_INDEX]
    resolved_kwargs = defaults[_RESOLVED_KWARGS_DEFAULT_INDEX]
    if type(factory) is not AdapterFactory or type(resolved_kwargs) is not dict:
        raise RuntimeError(f"Admitted {label} generated an unexpected adapter capture")
    if type(factory.kwargs) is not dict or not isinstance(factory.adapter_cls, type):
        raise RuntimeError(f"Admitted {label} generated an invalid adapter capture")
    if not issubclass(factory.adapter_cls, adapter_type):
        raise RuntimeError(f"Admitted {label} captured the wrong adapter kind")
    adapter_cls = cast(type[DataLoader] | type[DataSaver], factory.adapter_cls)

    contracts = {
        **adapter_cls.get_required_arguments(),
        **adapter_cls.get_optional_arguments(),
    }
    if set(resolved_kwargs) - set(contracts):
        raise RuntimeError(f"Admitted {label} captured an unknown adapter binding")
    for name, value in resolved_kwargs.items():
        contract = contracts[name]
        if not accepts(value, contract):
            raise TypeError(
                f"{adapter_cls.__qualname__}.{name}: bound {label} literal has wrong type"
            )


def _validate_captured_loader_literals(entries: Iterable[node.Node]) -> None:
    """Select the exact raw loader node before checking its fixed capture."""
    raw_entries = [entry for entry in entries if _loader_identity(entry, True) is not None]
    if len(raw_entries) != 1:
        raise RuntimeError("Admitted load_from produced an ambiguous raw loader node")
    _validate_captured_adapter_literals(
        raw_entries[0],
        expected_default_count=_LOAD_DATA_DEFAULT_COUNT,
        adapter_type=DataLoader,
        label="loader",
    )


def install_load_from_correction(modifier: LoadFromDecorator) -> LoadFromDecorator:
    """Install the correction on one already-copied exact Hamilton modifier.

    This is the compiler seam for Hamilton 1.90.0 only. The caller owns the
    enclosing version gate and must pass a copied, already-admitted exact
    ``LoadFromDecorator``. The wrapper delegates to the captured original bound
    method once, corrects only its returned raw/projection pair, and never scans
    unrelated resolved nodes or changes Hamilton's registry.
    """
    if type(modifier) is not LoadFromDecorator:
        raise TypeError("LoadFrom correction requires an exact LoadFromDecorator copy")
    if getattr(modifier, "__sdax_load_from_correction__", None) is _INSTALL_MARKER:
        return modifier

    modifier.loader_classes = tuple(modifier.loader_classes)
    modifier.kwargs = {
        name: copy(value) if type(value) in (LiteralDependency, UpstreamDependency) else value
        for name, value in modifier.kwargs.items()
    }
    original_get_loader_nodes = modifier.get_loader_nodes

    def corrected_get_loader_nodes(
        _self: LoadFromDecorator,
        inject_parameter: str,
        load_type: type[type],
        namespace: str | None = None,
    ) -> list[node.Node]:
        generated = original_get_loader_nodes(inject_parameter, load_type, namespace)
        _validate_captured_loader_literals(generated)
        return list(
            correct_load_from_annotations(
                generated,
                load_from_admitted=True,
            )
        )

    setattr(modifier, "get_loader_nodes", MethodType(corrected_get_loader_nodes, modifier))
    setattr(modifier, "__sdax_load_from_correction__", _INSTALL_MARKER)
    return modifier


def install_save_to_preflight(modifier: SaveToDecorator) -> SaveToDecorator:
    """Install literal validation on one copied exact Hamilton saver modifier.

    The caller owns the enclosing version gate and exact per-function admission.
    The wrapper calls the copied original method once, then checks only the
    selected factory and captured literal map on its returned saver node.
    """
    if type(modifier) is not SaveToDecorator:
        raise TypeError("SaveTo preflight requires an exact SaveToDecorator copy")
    if getattr(modifier, "__sdax_save_to_preflight__", None) is _INSTALL_MARKER:
        return modifier

    modifier.saver_classes = tuple(modifier.saver_classes)
    modifier.kwargs = {
        name: copy(value) if type(value) in (LiteralDependency, UpstreamDependency) else value
        for name, value in modifier.kwargs.items()
    }
    original_create_saver_node = modifier.create_saver_node

    def preflight_create_saver_node(
        _self: SaveToDecorator,
        node_: node.Node,
        config: dict[str, Any],
        fn: Any,
    ) -> node.Node:
        generated = original_create_saver_node(node_, config, fn)
        _validate_captured_adapter_literals(
            generated,
            expected_default_count=_SAVE_DATA_DEFAULT_COUNT,
            adapter_type=DataSaver,
            label="saver",
        )
        return generated

    setattr(modifier, "create_saver_node", MethodType(preflight_create_saver_node, modifier))
    setattr(modifier, "__sdax_save_to_preflight__", _INSTALL_MARKER)
    return modifier
