"""Public Driver qualification for configured models and delayed decorators."""

import logging
from typing import Any

import pytest

from sdax_hamilton import Driver


@pytest.mark.asyncio
@pytest.mark.parametrize("decorator_name", ["model", "dynamic_transform"])
async def test_configured_model_is_constructed_once_per_driver_and_keeps_state(
    module_factory, decorator_name
):
    events: list[str] = []
    instances: list[Any] = []
    settings = {"bias": 2}
    marker = object()
    module = module_factory(
        f"""
import pandas as pd
from hamilton.function_modifiers import {decorator_name}
from hamilton.models import BaseModel

class StatefulModel(BaseModel):
    def __init__(self, config_parameters, name, *, marker):
        super().__init__(config_parameters, name)
        self.marker = marker
        self.calls = 0
        instances.append(self)
        events.append("construct")

    def get_dependents(self):
        events.append("dependents")
        return ["series"]

    def predict(self, *, series):
        self.calls += 1
        return series + self.config_parameters["bias"] + self.calls

def series() -> pd.Series:
    return pd.Series([1])

@{decorator_name}(StatefulModel, "model_settings", marker=marker)
def result() -> pd.Series:
    pass
""",
        instances=instances,
        events=events,
        marker=marker,
    )

    driver = Driver(module, config={"model_settings": settings})
    first_plan = driver.prepare(["result"])
    second_plan = driver.prepare(["result"])

    assert len(instances) == 1
    assert events == ["construct", "dependents"]
    assert instances[0].config_parameters is settings
    assert instances[0].marker is marker
    assert (await first_plan.execute())["result"].tolist() == [4]
    assert (await second_plan.execute())["result"].tolist() == [5]
    assert instances[0].calls == 2
    assert events == ["construct", "dependents"]

    Driver(module, config={"model_settings": settings})
    assert len(instances) == 2
    assert events == ["construct", "dependents", "construct", "dependents"]


def test_pinned_model_config_filtering_defect_is_reproduced(hamilton_oracle):
    from hamilton.function_modifiers import base

    source = """
import pandas as pd
from hamilton.function_modifiers import model
from hamilton.models import BaseModel

class ExampleModel(BaseModel):
    def get_dependents(self):
        return []

    def predict(self):
        return pd.Series([1])

@model(ExampleModel, "model_settings")
def result() -> pd.Series:
    pass
"""

    with pytest.raises(base.InvalidDecoratorException, match="Configuration has no parameter"):
        hamilton_oracle(source, config={"model_settings": {}})


@pytest.mark.parametrize("decorator_name", ["model", "dynamic_transform"])
def test_configured_model_missing_config_uses_hamilton_required_config_error(
    module_factory, decorator_name
):
    from hamilton.function_modifiers import base

    module = module_factory(
        f"""
import pandas as pd
from hamilton.function_modifiers import {decorator_name}
from hamilton.models import BaseModel

class ExampleModel(BaseModel):
    def get_dependents(self):
        return []

    def predict(self):
        return pd.Series([1])

@{decorator_name}(ExampleModel, "model_settings")
def result() -> pd.Series:
    pass
"""
    )

    with pytest.raises(base.MissingConfigParametersException, match="model_settings"):
        Driver(module)


@pytest.mark.parametrize("decorator_name", ["model", "dynamic_transform"])
def test_configured_model_constructor_error_keeps_its_identity(module_factory, decorator_name):
    sentinel = ValueError("model settings sentinel")
    settings = object()
    module = module_factory(
        f"""
import pandas as pd
from hamilton.function_modifiers import {decorator_name}
from hamilton.models import BaseModel

class FailingModel(BaseModel):
    def __init__(self, config_parameters, name):
        raise sentinel

    def get_dependents(self):
        return []

    def predict(self):
        return pd.Series([1])

@{decorator_name}(FailingModel, "model_settings")
def result() -> pd.Series:
    pass
""",
        sentinel=sentinel,
    )

    with pytest.raises(ValueError) as caught:
        Driver(module, config={"model_settings": settings})

    assert caught.value is sentinel


@pytest.mark.asyncio
async def test_resolve_from_config_runs_once_per_driver_with_defaults(module_factory):
    calls: list[tuple[str, str]] = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, tag

@hamilton_exclude
def decorate_with(prefix: str, suffix: str = "!"):
    calls.append((prefix, suffix))
    return tag(resolved=prefix + suffix)

@resolve_from_config(decorate_with=decorate_with)
def result() -> int:
    return 7
""",
        calls=calls,
    )
    config = {"hamilton.enable_power_user_mode": True, "prefix": "ready"}

    driver = Driver(module, config=config)
    assert calls == [("ready", "!")]
    assert driver._nodes["result"].tags["resolved"] == "ready!"
    assert await driver.prepare(["result"]).execute() == {"result": 7}
    assert await driver.prepare(["result"]).execute() == {"result": 7}
    assert calls == [("ready", "!")]

    Driver(module, config=config)
    assert calls == [("ready", "!"), ("ready", "!")]


@pytest.mark.asyncio
async def test_resolve_runs_at_the_config_available_boundary(module_factory):
    calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import ResolveAt, hamilton_exclude, resolve, tag

@hamilton_exclude
def decorate_with(label: str):
    calls.append(label)
    return tag(resolved=label)

@resolve(when=ResolveAt.CONFIG_AVAILABLE, decorate_with=decorate_with)
def result() -> int:
    return 7
""",
        calls=calls,
    )
    config = {"hamilton.enable_power_user_mode": True, "label": "configured"}

    driver = Driver(module, config=config)
    assert calls == ["configured"]
    assert driver._nodes["result"].tags["resolved"] == "configured"
    assert await driver.prepare(["result"]).execute() == {"result": 7}
    assert calls == ["configured"]


@pytest.mark.parametrize("power_user_config", [{}, {"hamilton.enable_power_user_mode": False}])
def test_resolve_from_config_requires_explicit_power_user_mode(module_factory, power_user_config):
    module = module_factory(
        """
from hamilton.function_modifiers import resolve_from_config, tag

@resolve_from_config(decorate_with=lambda: tag(resolved="yes"))
def result() -> int:
    return 7
"""
    )

    with pytest.raises(Exception) as caught:
        Driver(module, config=power_user_config)

    assert "power user mode" in str(caught.value).lower() or isinstance(caught.value, KeyError)


def test_resolve_from_config_rejects_a_subclass_returned_modifier(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import resolve_from_config, tag

class AliasTag(tag):
    pass

@resolve_from_config(decorate_with=lambda: AliasTag(resolved="yes"))
def result() -> int:
    return 7
"""
    )

    with pytest.raises(ValueError, match="unsupported Hamilton decorator"):
        Driver(module, config={"hamilton.enable_power_user_mode": True})


def test_resolver_error_is_not_logged_by_hamilton(module_factory, caplog):
    sentinel = ValueError("resolver predicate sentinel")
    calls: list[str] = []
    module = module_factory(
        """
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config, tag

@hamilton_exclude
def decorate_with():
    calls.append("resolve")
    raise sentinel

@resolve_from_config(decorate_with=decorate_with)
def result() -> int:
    return 7
""",
        calls=calls,
        sentinel=sentinel,
    )

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as caught:
            Driver(module, config={"hamilton.enable_power_user_mode": True})

    assert caught.value is sentinel
    assert calls == ["resolve"]
    assert not [
        record for record in caplog.records if record.name == "hamilton.function_modifiers.base"
    ]
