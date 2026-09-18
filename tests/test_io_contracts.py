"""Pinned Hamilton I/O contracts that phase F must preserve on admission."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from hamilton import node
from hamilton.function_modifiers import base, dataloader, datasaver, load_from, save_to
from hamilton.function_modifiers.adapters import InvalidDecoratorException
from hamilton.io.data_adapters import DataLoader, DataSaver
from hamilton.registry import LOADER_REGISTRY, SAVER_REGISTRY


def _registry_name() -> str:
    return "sdax_hamilton_test_" + uuid4().hex


def test_load_from_preserves_last_registered_adapter_and_captures_it_before_execution(
    monkeypatch,
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class First(DataLoader):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            self.events.append("first")
            return 1, {"source": "first"}

    @dataclass
    class Second(DataLoader):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            self.events.append("second")
            return 2, {"source": "second"}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [First, Second])
    modifier = getattr(load_from, registry_name)(events=events)
    raw, projection = modifier.get_loader_nodes("item", int, "consumer")
    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [First])

    assert events == []
    assert raw.tags["hamilton.data_loader.classname"] == Second.__qualname__
    assert projection.tags["hamilton.data_loader.classname"] == Second.__qualname__
    assert raw.callable() == (2, {"source": "second"})
    assert events == ["second"]


def test_save_to_preserves_last_registered_adapter_and_target_contract(monkeypatch):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class First(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append(f"first:{data}")
            return {"sink": "first"}

    @dataclass
    class Second(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append(f"second:{data}")
            return {"sink": "second"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [First, Second])
    modifier = getattr(save_to, registry_name)(events=events, output_name_="stored")

    def result(value: int) -> int:
        return value

    generated = list(modifier.transform_node(node.Node.from_fn(result), {}, result))
    saved = generated[0]
    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [First])

    assert events == []
    assert saved.input_types["result"][0] is int
    assert saved.tags["hamilton.data_saver.classname"] == Second.__qualname__
    assert saved.callable(result=7) == {"sink": "second"}
    assert events == ["second:7"]


def test_dataloader_keeps_raw_metadata_tuple_and_projected_data_contract():
    events: list[str] = []

    def item() -> tuple[int, dict[str, Any]]:
        events.append("load")
        return 7, {"source": "memory"}

    item.__name__ = "item"
    raw, projection = base.resolve_nodes(dataloader()(item), {})

    assert events == []
    assert raw.type == tuple[int, dict[str, Any]]
    assert projection.input_types[raw.name][0] == raw.type
    value = raw.callable()
    assert value == (7, {"source": "memory"})
    assert projection.callable(**{raw.name: value}) == 7
    assert events == ["load"]


def test_datasaver_requires_the_pinned_exact_builtin_dict_return_type():
    def valid(data: int) -> dict:
        return {"saved": data}

    def invalid(data: int) -> dict[str, Any]:
        return {"saved": data}

    valid_node = tuple(base.resolve_nodes(datasaver()(valid), {}))[0]
    assert valid_node.type is dict
    assert valid_node.tags["hamilton.data_saver.classname"] == "valid()"

    with pytest.raises(InvalidDecoratorException, match="must return a dict"):
        base.resolve_nodes(datasaver()(invalid), {})
