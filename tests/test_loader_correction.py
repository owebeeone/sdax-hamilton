"""Regression coverage for Hamilton 1.90.0 generated ``load_from`` annotations."""

from copy import copy
from dataclasses import dataclass
from typing import Any

import pytest
from hamilton.function_modifiers import base, dataloader
from hamilton.function_modifiers.adapters import LoadFromDecorator
from hamilton.io.data_adapters import DataLoader

from sdax_hamilton._hamilton_loader import (
    correct_load_from_annotations,
    install_load_from_correction,
)
from sdax_hamilton._types import accepts


@dataclass
class _MemoryIntegerLoader(DataLoader):
    calls: list[str]

    @classmethod
    def applicable_types(cls):
        return [int]

    @classmethod
    def name(cls) -> str:
        return "memory-integer"

    def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
        self.calls.append("load")
        return 7, {"source": "memory"}


def _generated_loader_pair(calls: list[str]):
    return tuple(
        LoadFromDecorator((_MemoryIntegerLoader,), calls=calls).get_loader_nodes(
            "item", int, "consumer"
        )
    )


def test_corrects_raw_tuple_and_preserves_projection_without_pregraph_io():
    calls: list[str] = []
    raw, projection = _generated_loader_pair(calls)

    corrected_raw, corrected_projection = correct_load_from_annotations(
        (raw, projection), load_from_admitted=True
    )

    assert calls == []
    assert raw.type == tuple[dict[str, Any], int]
    assert projection.input_types[raw.name][0] == raw.type
    assert corrected_raw.type == tuple[int, dict[str, Any]]
    assert corrected_projection.input_types[raw.name][0] == corrected_raw.type

    value = corrected_raw.callable()
    assert value == (7, {"source": "memory"})
    assert accepts(value, corrected_raw.type)
    assert not accepts(({"source": "memory"}, 7), corrected_raw.type)
    assert corrected_projection.callable(**{corrected_raw.name: value}) == 7
    assert accepts(corrected_projection.callable(**{corrected_raw.name: value}), int)
    assert calls == ["load"]


def test_invalid_loader_contents_remain_rejected_by_raw_and_projection_checks():
    raw, projection = _generated_loader_pair([])
    corrected_raw, corrected_projection = correct_load_from_annotations(
        (raw, projection), load_from_admitted=True
    )
    invalid = ("wrong", {"source": "memory"})

    assert not accepts(invalid, corrected_raw.type)
    assert corrected_projection.callable(**{corrected_raw.name: invalid}) == "wrong"
    assert not accepts(corrected_projection.callable(**{corrected_raw.name: invalid}), int)


def test_correction_is_idempotent_and_does_not_mutate_generated_snapshot():
    raw, projection = _generated_loader_pair([])
    corrected = correct_load_from_annotations((raw, projection), load_from_admitted=True)
    corrected_again = correct_load_from_annotations(corrected, load_from_admitted=True)

    corrected_raw, corrected_projection = corrected
    assert corrected_again == corrected
    assert corrected_again[0] is corrected_raw
    assert corrected_again[1] is corrected_projection
    assert corrected_raw is not raw
    assert corrected_projection is not projection
    raw.tags["hamilton.data_loader.node"] = "changed-after-correction"
    projection.input_types[raw.name] = (str, projection.input_types[raw.name][1])
    assert corrected_raw.tags["hamilton.data_loader.node"] == "item"
    assert corrected_projection.input_types[raw.name][0] == tuple[int, dict[str, Any]]


def test_tagged_nodes_do_not_activate_without_admitted_load_from_context():
    raw, projection = _generated_loader_pair([])

    unchanged = correct_load_from_annotations((raw, projection), load_from_admitted=False)

    assert unchanged == (raw, projection)
    assert unchanged[0] is raw
    assert unchanged[1] is projection


def test_real_dataloader_tags_do_not_activate_the_load_from_correction():
    def item() -> tuple[int, dict[str, Any]]:
        return 7, {"source": "memory"}

    item.__name__ = "item"
    entries = tuple(base.resolve_nodes(dataloader()(item), {}))
    raw, projection = entries

    unchanged = correct_load_from_annotations(entries, load_from_admitted=False)

    assert raw.type == tuple[int, dict[str, Any]]
    assert projection.input_types[raw.name][0] == raw.type
    assert unchanged[0] is raw
    assert unchanged[1] is projection


@pytest.mark.parametrize("version_source", ["distribution", "imported"])
def test_enclosing_compatibility_gate_rejects_other_hamilton_versions(monkeypatch, version_source):
    from sdax_hamilton import hamilton_compat

    if version_source == "distribution":
        monkeypatch.setattr(hamilton_compat.metadata, "version", lambda _: "1.91.0")
    else:
        monkeypatch.setattr(hamilton_compat.hamilton, "__version__", (1, 91, 0))

    with pytest.raises(RuntimeError, match="Unsupported Hamilton version"):
        hamilton_compat._check_version()


def test_admitted_unexpected_generated_shape_fails_closed():
    raw, projection = _generated_loader_pair([])
    projection.input_types[raw.name] = (tuple[int, dict[str, Any]], projection.input_types[raw.name][1])

    with pytest.raises(RuntimeError, match="unexpected raw loader annotation"):
        correct_load_from_annotations((raw, projection), load_from_admitted=True)


def test_copied_load_from_wrapper_corrects_only_its_generated_pair_and_snapshots_bindings():
    calls: list[str] = []
    changed_calls: list[str] = []
    loader_classes = [_MemoryIntegerLoader]
    application_modifier = LoadFromDecorator(loader_classes, calls=calls)
    copied_modifier = install_load_from_correction(copy(application_modifier))

    loader_classes.clear()
    application_modifier.kwargs["calls"] = changed_calls
    raw, projection = copied_modifier.get_loader_nodes("item", int, "consumer")

    assert application_modifier.loader_classes == []
    assert application_modifier.kwargs["calls"] is changed_calls
    assert copied_modifier.loader_classes == (_MemoryIntegerLoader,)
    assert copied_modifier.kwargs["calls"] is calls
    assert raw.type == tuple[int, dict[str, Any]]
    assert projection.input_types[raw.name][0] == raw.type
    assert raw.callable() == (7, {"source": "memory"})
    assert calls == ["load"]
    assert changed_calls == []
    assert install_load_from_correction(copied_modifier) is copied_modifier
