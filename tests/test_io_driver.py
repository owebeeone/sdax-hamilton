"""Driver/PreparedPlan qualification for the finite phase-F I/O admission."""

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import pytest
from hamilton.function_modifiers.expanders import extract_fields
from hamilton.io.data_adapters import DataLoader, DataSaver
from hamilton.registry import LOADER_REGISTRY, SAVER_REGISTRY

from sdax_hamilton import Driver, hamilton_compat
from sdax_hamilton._model import GeneratedRole


def _registry_name() -> str:
    return "sdax_hamilton_driver_test_" + uuid4().hex


@pytest.mark.asyncio
async def test_load_from_driver_snapshots_selected_registry_adapter_and_keeps_raw_public(
    module_factory, monkeypatch
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
    source = f"""
from hamilton.function_modifiers import load_from
@load_from.{registry_name}(events=events)
def result(item: int) -> int:
    return item
"""
    driver_a = Driver(module_factory(source, events=events))
    raw_name = next(
        name
        for name, spec in driver_a._nodes.items()
        if spec.tags.get("hamilton.data_loader.has_metadata") is True
    )
    projection_name = next(
        name
        for name, spec in driver_a._nodes.items()
        if spec.tags.get("hamilton.data_loader.has_metadata") is False
    )
    assert driver_a._nodes[raw_name].role is GeneratedRole.VALUE
    assert driver_a._nodes[projection_name].role is GeneratedRole.PROJECTION
    assert not driver_a._nodes[raw_name].ownership_required
    driver_a.prepare(["result"])
    assert events == []

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [First])
    driver_b = Driver(module_factory(source, events=events))

    assert await driver_a.prepare([raw_name]).execute() == {
        raw_name: (2, {"source": "second"})
    }
    assert await driver_b.prepare(["result"]).execute() == {"result": 1}
    assert events == ["second", "first"]


def test_load_from_bad_literal_fails_before_adapter_construction(module_factory, monkeypatch):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Loader(DataLoader):
        threshold: int
        events: list[str]

        def __post_init__(self) -> None:
            self.events.append("construct")

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            self.events.append("load")
            return self.threshold, {}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    source = f"""
from hamilton.function_modifiers import load_from
@load_from.{registry_name}(threshold="wrong", events=events)
def result(item: int) -> int:
    return item
"""

    with pytest.raises((TypeError, ValueError)):
        Driver(module_factory(source, events=events))
    assert events == []


@pytest.mark.asyncio
async def test_load_from_bad_config_binding_fails_before_adapter_construction(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Loader(DataLoader):
        threshold: int
        events: list[str]

        def __post_init__(self) -> None:
            self.events.append("construct")

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            self.events.append("load")
            return self.threshold, {}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    source = f"""
from hamilton.function_modifiers import load_from, source
@load_from.{registry_name}(threshold=source("threshold"), events=events)
def result(item: int) -> int:
    return item
"""
    plan = Driver(module_factory(source, events=events)).prepare(["result"])

    with pytest.raises(TypeError, match="Invalid input"):
        await plan.execute(inputs={"threshold": "wrong"})
    assert events == []


def test_load_from_missing_adapter_binding_fails_before_adapter_construction(module_factory, monkeypatch):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Loader(DataLoader):
        threshold: int

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            events.append("load")
            return self.threshold, {}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    source = f"""
from hamilton.function_modifiers import load_from
@load_from.{registry_name}()
def result(item: int) -> int:
    return item
"""

    with pytest.raises(Exception):
        Driver(module_factory(source))
    assert events == []


@pytest.mark.asyncio
async def test_dataloader_raw_tuple_and_projection_remain_public_driver_outputs(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import dataloader
@dataloader()
def item() -> tuple[int, dict[str, str]]:
    events.append("load")
    return 7, {"source": "memory"}
""",
        events=events,
    )
    driver = Driver(module)

    assert driver._nodes["item.loader"].role is GeneratedRole.VALUE
    assert driver._nodes["item"].role is GeneratedRole.PROJECTION
    assert events == []
    assert await driver.prepare(["item"]).execute() == {"item": 7}
    assert await driver.prepare(["item.loader"]).execute() == {
        "item.loader": (7, {"source": "memory"})
    }
    assert events == ["load", "load"]


@pytest.mark.asyncio
async def test_dataloader_shutdown_owns_raw_tuple_and_projection_borrows_it(module_factory):
    """A projected value remains live only within the raw loader owner's scope."""
    events: list[str] = []

    class Handle:
        def __init__(self) -> None:
            self.live = True

    module = module_factory(
        """
from hamilton.function_modifiers import dataloader
from sdax_hamilton import Acquisition, shutdown
@dataloader()
def item() -> tuple[Handle, dict[str, str]]:
    events.append("load")
    return Handle(), {"source": "memory"}
@shutdown(of=item)
def close(state: Acquisition[tuple[Handle, dict[str, str]]]) -> None:
    raw = state.value
    assert raw[0].live
    raw[0].live = False
    events.append("release:" + raw[1]["source"])
""",
        events=events,
        Handle=Handle,
    )
    driver = Driver(module)
    plan = driver.prepare(["item"])

    assert driver._nodes["item.loader"].role is GeneratedRole.VALUE
    assert driver._nodes["item.loader"].ownership_required
    assert driver._nodes["item.loader"].release is not None
    assert driver._nodes["item"].role is GeneratedRole.PROJECTION
    assert driver._nodes["item"].borrow_from == frozenset({"item.loader"})
    with pytest.raises(ValueError, match=r"open\(\)"):
        await plan.execute()
    async with plan.open() as values:
        assert values["item"].live
        assert events == ["load"]
    assert events == ["load", "release:memory"]


def test_dataloader_policy_targets_its_raw_actual_call_not_projection(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import dataloader
from sdax_hamilton import execution
@execution(target_="item", timeout=2.0, retries=1)
@dataloader()
def item() -> tuple[int, dict[str, str]]:
    events.append("load")
    return 7, {"source": "memory"}
""",
        events=events,
    )
    driver = Driver(module)

    raw_policy = driver._nodes["item.loader"].policy
    projection_policy = driver._nodes["item"].policy
    assert (raw_policy.timeout, raw_policy.retries) == (2.0, 1)
    assert (projection_policy.timeout, projection_policy.retries) == (None, 0)
    assert events == []


@pytest.mark.asyncio
async def test_explicit_load_from_raw_target_routes_retry_without_preconstruction_effect(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Loader(DataLoader):
        events: list[str]

        def __post_init__(self) -> None:
            self.events.append("construct")

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            self.events.append("load")
            if self.events.count("load") == 1:
                raise TimeoutError("retry")
            return 7, {"source": "memory"}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    module = module_factory(
        f"""
from hamilton.function_modifiers import load_from
from sdax_hamilton import execution
@execution(
    target_="result.load_data.item", timeout=1.0, retries=1,
    initial_delay=0.0, backoff_factor=1.0,
)
@load_from.{registry_name}(events=events)
def result(item: int) -> int:
    return item
def unrelated() -> int:
    return 3
""",
        events=events,
    )
    driver = Driver(module)

    raw_name = "result.load_data.item"
    raw_policy = driver._nodes[raw_name].policy
    assert (raw_policy.timeout, raw_policy.retries) == (1.0, 1)
    assert driver._nodes["result"].policy.timeout is None
    assert driver._nodes["unrelated"].policy.timeout is None
    assert events == []
    assert await driver.prepare(["result"]).execute() == {"result": 7}
    assert events == ["construct", "load", "construct", "load"]


def test_default_load_from_policy_stays_on_the_declared_consumer(module_factory, monkeypatch):
    registry_name = _registry_name()

    @dataclass
    class Loader(DataLoader):
        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[int, dict[str, Any]]:
            return 7, {"source": "memory"}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    module = module_factory(
        f"""
from hamilton.function_modifiers import load_from
from sdax_hamilton import execution
@execution(timeout=2.0, retries=1)
@load_from.{registry_name}()
def result(item: int) -> int:
    return item
"""
    )
    driver = Driver(module)

    assert driver._nodes["result"].policy.timeout == 2.0
    assert driver._nodes["result.load_data.item"].policy.timeout is None


@pytest.mark.asyncio
async def test_loader_input_can_feed_a_real_sdax_acquisition_with_normal_release(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    class Handle:
        pass

    @dataclass
    class Loader(DataLoader):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [Handle]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def load_data(self, type_: type) -> tuple[Handle, dict[str, Any]]:
            self.events.append("load")
            return Handle(), {"source": "memory"}

    monkeypatch.setitem(LOADER_REGISTRY, registry_name, [Loader])
    source = f"""
from hamilton.function_modifiers import load_from
from sdax_hamilton import Acquisition, shutdown
@load_from.{registry_name}(events=events)
def acquire(handle: Handle) -> Handle:
    return handle
@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    events.append("release")
def result(acquire: Handle) -> int:
    return 1
"""
    driver = Driver(module_factory(source, events=events, Handle=Handle))

    raw_name = next(
        name
        for name, spec in driver._nodes.items()
        if spec.tags.get("hamilton.data_loader.has_metadata") is True
    )
    assert driver._nodes[raw_name].role is GeneratedRole.VALUE
    assert driver._nodes["acquire"].ownership_required
    assert driver._nodes["acquire"].release is not None
    assert not driver._nodes[raw_name].ownership_required
    assert await driver.prepare(["result"]).execute() == {"result": 1}
    assert events == ["load", "release"]


@pytest.mark.asyncio
async def test_save_to_target_emits_metadata_only_when_sink_is_selected(module_factory, monkeypatch):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append(f"save:{data}")
            return {"sink": "memory"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    source = f"""
from hamilton.function_modifiers import save_to
@save_to.{registry_name}(events=events, output_name_="sink", target_="result")
def result() -> int:
    return 7
"""
    driver = Driver(module_factory(source, events=events))

    assert driver._nodes["sink"].role is GeneratedRole.VALUE
    assert not driver._nodes["sink"].ownership_required
    assert await driver.prepare(["result"]).execute() == {"result": 7}
    assert events == []
    assert await driver.prepare(["sink"]).execute() == {"sink": {"sink": "memory"}}
    assert events == ["save:7"]


@pytest.mark.asyncio
async def test_save_to_metadata_sink_keeps_owned_producer_live_until_saved(
    module_factory, monkeypatch
):
    """The saver consumes its owned input, then cleanup precedes metadata return."""
    events: list[str] = []
    registry_name = _registry_name()

    class Handle:
        def __init__(self) -> None:
            self.live = True

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [Handle]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: Handle) -> dict[str, Any]:
            assert data.live
            self.events.append("save")
            return {"sink": "memory"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import save_to
from sdax_hamilton import Acquisition, shutdown
@save_to.{registry_name}(events=events, output_name_="sink")
def acquire() -> Handle:
    events.append("acquire")
    return Handle()
@shutdown(of=acquire)
def close(state: Acquisition[Handle]) -> None:
    handle = state.value
    assert handle.live
    handle.live = False
    events.append("release")
""",
        events=events,
        Handle=Handle,
    )
    driver = Driver(module)

    assert driver._nodes["acquire"].ownership_required
    assert driver._nodes["sink"].borrow_from == frozenset()
    assert await driver.prepare(["sink"]).execute() == {"sink": {"sink": "memory"}}
    assert events == ["acquire", "save", "release"]


@pytest.mark.asyncio
async def test_datasaver_keeps_its_effect_metadata_as_a_public_value(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import datasaver
@datasaver()
def saved(value: int) -> dict:
    events.append(f"save:{value}")
    return {"destination": "memory"}
""",
        events=events,
    )
    driver = Driver(module)

    assert driver._nodes["saved"].role is GeneratedRole.VALUE
    assert await driver.prepare(["saved"]).execute(inputs={"value": 7}) == {
        "saved": {"destination": "memory"}
    }
    assert events == ["save:7"]


def test_datasaver_policy_targets_its_actual_effect_node_without_running_it(module_factory):
    events: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import datasaver
from sdax_hamilton import execution
@execution(target_="saved", timeout=3.0, retries=2)
@datasaver()
def saved(value: int) -> dict:
    events.append(f"save:{value}")
    return {"destination": "memory"}
""",
        events=events,
    )
    driver = Driver(module)

    policy = driver._nodes["saved"].policy
    assert (policy.timeout, policy.retries) == (3.0, 2)
    assert events == []


@pytest.mark.asyncio
async def test_explicit_save_to_sink_target_routes_retry_without_repeating_producer(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        def __post_init__(self) -> None:
            self.events.append("construct")

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append("save")
            if self.events.count("save") == 1:
                raise TimeoutError("retry")
            return {"destination": "memory", "data": data}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import save_to
from sdax_hamilton import execution
@execution(
    target_="sink", timeout=1.0, retries=1,
    initial_delay=0.0, backoff_factor=1.0,
)
@save_to.{registry_name}(events=events, output_name_="sink")
def result() -> int:
    events.append("produce")
    return 7
def unrelated() -> int:
    return 3
""",
        events=events,
    )
    driver = Driver(module)

    sink_policy = driver._nodes["sink"].policy
    assert (sink_policy.timeout, sink_policy.retries) == (1.0, 1)
    assert driver._nodes["result"].policy.timeout is None
    assert driver._nodes["unrelated"].policy.timeout is None
    assert events == []
    assert await driver.prepare(["sink"]).execute() == {
        "sink": {"destination": "memory", "data": 7}
    }
    assert events == ["produce", "construct", "save", "construct", "save"]


def test_shutdown_cannot_target_synthetic_save_to_effect(module_factory, monkeypatch):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            events.append("save")
            return {"destination": "memory"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import save_to
from sdax_hamilton import Acquisition, shutdown
@save_to.{registry_name}(output_name_="sink")
def result() -> int:
    events.append("produce")
    return 7
@shutdown(of=result, target_="sink")
def close(state: Acquisition[int]) -> None:
    events.append("release")
""",
        events=events,
    )

    with pytest.raises(ValueError, match=r"targets not generated: \['sink'\]"):
        Driver(module)
    assert events == []


def test_shutdown_target_can_name_an_extract_fields_projection(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import extract_fields
from sdax_hamilton import Acquisition, shutdown
@extract_fields({"number": int})
def acquire() -> dict[str, int]:
    return {"number": 7}
@shutdown(of=acquire, target_="number")
def close(state: Acquisition[dict[str, int]]) -> None:
    pass
"""
    )

    specs = hamilton_compat.compile_modules(
        (module,),
        {},
        _supported=(*hamilton_compat._SUPPORTED, extract_fields),
    )
    assert specs["acquire"].ownership_required
    assert specs["acquire"].release is not None


def test_datasaver_rejects_generic_dictionary_annotation_before_effect(module_factory):
    events: list[str] = []
    with pytest.raises(Exception, match="must return a dict"):
        module_factory(
            """
from hamilton.function_modifiers import datasaver
@datasaver()
def saved() -> dict[str, str]:
    events.append("save")
    return {"destination": "memory"}
""",
            events=events,
        )
    assert events == []


@pytest.mark.asyncio
async def test_save_to_sink_runs_after_its_upstream_validation_gate(module_factory, monkeypatch):
    """The saver consumes the validated result instead of the raw declaration."""
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append(f"save:{data}")
            return {"sink": "memory"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import check_output, save_to
@save_to.{registry_name}(events=events, output_name_="sink", target_="checked")
@check_output(range=(0, 10))
def checked() -> int:
    return 7
""",
        events=events,
    )
    driver = Driver(module)

    assert driver._nodes["sink"].role is GeneratedRole.VALUE
    assert driver._nodes["sink"].inputs["checked"].typ is int
    assert await driver.prepare(["sink"]).execute() == {"sink": {"sink": "memory"}}
    assert events == ["save:7"]


@pytest.mark.asyncio
async def test_validated_save_to_sink_can_be_the_explicit_retry_policy_target(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        def __post_init__(self) -> None:
            self.events.append("construct")

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append("save")
            if self.events.count("save") == 1:
                raise TimeoutError("retry")
            return {"sink": "memory", "data": data}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import check_output, save_to
from sdax_hamilton import execution
@execution(
    target_="sink", timeout=1.0, retries=1,
    initial_delay=0.0, backoff_factor=1.0,
)
@save_to.{registry_name}(events=events, output_name_="sink", target_="checked")
@check_output(range=(0, 10))
def checked() -> int:
    events.append("produce")
    return 7
""",
        events=events,
    )
    driver = Driver(module)

    policy = driver._nodes["sink"].policy
    assert (policy.timeout, policy.retries) == (1.0, 1)
    assert events == []
    assert await driver.prepare(["sink"]).execute() == {
        "sink": {"sink": "memory", "data": 7}
    }
    assert events == ["produce", "construct", "save", "construct", "save"]


@pytest.mark.asyncio
async def test_namespaced_binding_contract_survives_save_to_before_invalid_input_effects(
    module_factory, monkeypatch
):
    events: list[str] = []
    registry_name = _registry_name()

    @dataclass
    class Saver(DataSaver):
        events: list[str]

        @classmethod
        def applicable_types(cls):
            return [int]

        @classmethod
        def name(cls) -> str:
            return registry_name

        def save_data(self, data: int) -> dict[str, Any]:
            self.events.append(f"save:{data}")
            return {"destination": "memory"}

    monkeypatch.setitem(SAVER_REGISTRY, registry_name, [Saver])
    module = module_factory(
        f"""
from hamilton.function_modifiers import inject, parameterized_subdag, save_to, source
@save_to.{registry_name}(events=events, output_name_="stored")
@inject(left=source("shared"))
def component(left: int, shared: int | str = 3) -> int:
    events.append(f"produce:{{left}}")
    return left
@parameterized_subdag(component, low={{}})
def result(component: int) -> int:
    return component
""",
        events=events,
    )
    driver = Driver(module)
    stored_name = next(
        name
        for name, spec in driver._nodes.items()
        if name.startswith("low.") and spec.tags.get("hamilton.data_saver")
    )
    component_name = next(name for name in driver._nodes if name.endswith(".component"))
    shared = driver._nodes[component_name].inputs["shared"]

    assert shared.typ == int | str
    assert shared.default == 3
    assert shared.requirements == (int, int | str)
    with pytest.raises(TypeError, match="Invalid input: shared"):
        await driver.prepare([stored_name], optional_inputs=["shared"]).execute(
            inputs={"shared": "wrong"}
        )
    assert events == []
