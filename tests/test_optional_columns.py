"""Qualified exact Polars ``with_columns`` capture through the real frontend."""

import os
from functools import partial

import pytest

if os.environ.get("SDAX_HAMILTON_TEST_PROFILE") != "polars":
    pytest.skip("requires SDAX_HAMILTON_TEST_PROFILE=polars", allow_module_level=True)

import polars as pl
from hamilton import settings
from hamilton.function_modifiers import pipe_input, pipe_output
from hamilton.function_modifiers.delayed import resolve_from_config
from hamilton.function_modifiers.validation import check_output_custom
from hamilton.plugins.h_polars import with_columns as eager_with_columns
from hamilton.plugins.h_polars_lazyframe import with_columns as lazy_with_columns

from sdax_hamilton import Driver, hamilton_compat
from sdax_hamilton import driver as driver_module
from sdax_hamilton._model import GeneratedRole


def _admit(monkeypatch, *modifier_types):
    monkeypatch.setattr(
        driver_module,
        "compile_modules",
        partial(
            hamilton_compat.compile_modules,
            _supported=(*hamilton_compat._SUPPORTED, *modifier_types),
        ),
    )


@pytest.mark.asyncio
async def test_eager_columns_preserve_nested_owner_and_snapshot(module_factory, monkeypatch):
    _admit(monkeypatch, eager_with_columns, check_output_custom)
    events: list[object] = []
    module = module_factory(
        """
import polars as pl
from hamilton.data_quality import base as data_quality
from hamilton.plugins.h_polars import with_columns
from hamilton.function_modifiers import check_output_custom
from sdax_hamilton import Acquisition, execution, shutdown

class SeriesValidator(data_quality.DataValidator):
    def __init__(self):
        super().__init__("fail")

    @classmethod
    def name(cls):
        return "series_ok"

    def applies_to(self, datatype):
        return datatype is pl.Series

    def description(self):
        return "series is nonempty"

    def validate(self, dataset):
        return data_quality.ValidationResult(
            passes=len(dataset) > 0,
            message="series check",
            diagnostics={},
        )

@check_output_custom(SeriesValidator())
@execution(timeout=1)
def total(left: pl.Series, right: pl.Series) -> pl.Series:
    events.append("total")
    return left + right

@shutdown(of=total)
def close_total(state: Acquisition[pl.Series]) -> None:
    events.append(("close", state.value.to_list()))

@with_columns(total, columns_to_pass=["left", "right"], select=["total"], namespace="metrics")
def enriched(frame: pl.DataFrame) -> pl.DataFrame:
    return frame

def changed(left: pl.Series, right: pl.Series) -> pl.Series:
    return left * right
""",
        events=events,
    )
    driver = Driver(module)
    modifier = module.enriched.inject[0]
    module.total.__code__ = module.changed.__code__
    modifier.select[:] = ["not_captured"]
    modifier.initial_schema[:] = ["not_captured"]
    frame = pl.DataFrame({"left": [1, 2], "right": [3, 4]})

    result = await driver.prepare(["enriched"]).execute(inputs={"frame": frame})

    assert result["enriched"].to_dict(as_series=False) == {
        "left": [1, 2],
        "right": [3, 4],
        "total": [4, 6],
    }
    helper = driver._nodes["metrics.total_raw"]
    assert helper.origin.endswith(".total")
    assert helper.policy.timeout == 1
    assert helper.ownership_required
    assert helper.release is not None
    assert helper.role is GeneratedRole.VALIDATION_RAW
    assert driver._nodes["metrics.total"].origin.endswith(".total")
    assert driver._nodes["metrics.total"].role is GeneratedRole.VALIDATION_GATE
    assert driver._nodes["metrics.total_series_ok"].role is GeneratedRole.VALIDATION_EVIDENCE
    assert driver._nodes["metrics._append"].borrow_from == frozenset(
        {"metrics.total_raw"}
    )
    assert events == ["total", ("close", [4, 6])]


@pytest.mark.asyncio
async def test_lazy_columns_remain_lazy_and_keep_nested_origin(module_factory, monkeypatch):
    _admit(monkeypatch, lazy_with_columns)
    module = module_factory(
        """
import polars as pl
from hamilton.plugins.h_polars_lazyframe import with_columns

def total(left: pl.Expr, right: pl.Expr) -> pl.Expr:
    return left + right

@with_columns(total, columns_to_pass=["left", "right"], select=["total"], namespace="metrics")
def enriched(frame: pl.LazyFrame) -> pl.LazyFrame:
    return frame
"""
    )
    driver = Driver(module)
    frame = pl.DataFrame({"left": [2], "right": [5]}).lazy()

    result = await driver.prepare(["enriched"]).execute(inputs={"frame": frame})

    assert isinstance(result["enriched"], pl.LazyFrame)
    assert result["enriched"].collect().to_dict(as_series=False) == {
        "left": [2],
        "right": [5],
        "total": [7],
    }
    assert driver._nodes["metrics.total"].origin.endswith(".total")
    assert not driver._nodes["metrics.left"].ownership_required


@pytest.mark.parametrize(("mode", "expected"), (("sum", 7), ("difference", 3)))
@pytest.mark.asyncio
async def test_columns_select_one_configured_nested_declaration(
    module_factory, monkeypatch, mode, expected
):
    _admit(monkeypatch, eager_with_columns)
    module = module_factory(
        """
import polars as pl
from hamilton.function_modifiers import config
from hamilton.plugins.h_polars import with_columns

@config.when(mode="sum")
def selected__sum(left: pl.Series, right: pl.Series) -> pl.Series:
    return left + right

@config.when(mode="difference")
def selected__difference(left: pl.Series, right: pl.Series) -> pl.Series:
    return left - right

@with_columns(
    selected__sum,
    selected__difference,
    columns_to_pass=["left", "right"],
    select=["selected"],
    namespace="metrics",
)
def enriched(frame: pl.DataFrame) -> pl.DataFrame:
    return frame
"""
    )
    driver = Driver(module, config={"mode": mode})

    result = await driver.prepare(["enriched"]).execute(
        inputs={"frame": pl.DataFrame({"left": [5], "right": [2]})}
    )

    assert result["enriched"]["selected"].to_list() == [expected]
    assert driver._nodes["metrics.selected"].origin.endswith(f".selected__{mode}")


@pytest.mark.asyncio
async def test_delayed_columns_select_once_and_use_the_same_capture_path(
    module_factory, monkeypatch
):
    _admit(monkeypatch, resolve_from_config, eager_with_columns)
    resolver_calls: list[str] = []
    module = module_factory(
        """
import polars as pl
from hamilton.function_modifiers import hamilton_exclude, resolve_from_config
from hamilton.plugins.h_polars import with_columns

def total(left: pl.Series, right: pl.Series) -> pl.Series:
    return left + right

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return with_columns(
        total,
        columns_to_pass=["left", "right"],
        select=["total"],
        namespace="metrics",
    )

@resolve_from_config(decorate_with=decorate_with)
def enriched(frame: pl.DataFrame) -> pl.DataFrame:
    return frame
""",
        resolver_calls=resolver_calls,
    )
    driver = Driver(module, config={settings.ENABLE_POWER_USER_MODE: True})
    assert resolver_calls == ["resolve"]

    frame = pl.DataFrame({"left": [3], "right": [4]})
    result = await driver.prepare(["enriched"]).execute(inputs={"frame": frame})

    assert result["enriched"]["total"].to_list() == [7]
    assert driver._nodes["metrics.total"].origin.endswith(".total")
    assert resolver_calls == ["resolve"]


@pytest.mark.asyncio
async def test_pipeline_default_survives_columns_namespace(module_factory, monkeypatch):
    _admit(monkeypatch, pipe_output, eager_with_columns)
    fallback = pl.Series([2])
    module = module_factory(
        """
import polars as pl
from hamilton.function_modifiers import pipe_output, step
from hamilton.plugins.h_polars import with_columns

def increment(value: pl.Series = fallback) -> pl.Series:
    return value + 1

@pipe_output(step(increment))
def total(left: pl.Series) -> pl.Series:
    return left

@with_columns(total, columns_to_pass=["left"], select=["total"], namespace="metrics")
def enriched(frame: pl.DataFrame) -> pl.DataFrame:
    return frame
""",
        fallback=fallback,
    )
    driver = Driver(module)

    result = await driver.prepare(["enriched"]).execute(
        inputs={"frame": pl.DataFrame({"left": [3, 5]})}
    )

    assert result["enriched"].to_dict(as_series=False) == {
        "left": [3, 5],
        "total": [4, 6],
    }
    generated = driver._nodes["metrics.total.with_increment"]
    assert generated.inputs["metrics.total.raw"].requirements == (pl.Series,)
    assert generated.inputs["metrics.total.raw"].default is fallback


@pytest.mark.asyncio
async def test_columns_namespace_keeps_merged_pipeline_requirements_before_callbacks(
    module_factory, monkeypatch
):
    _admit(monkeypatch, resolve_from_config, pipe_input, eager_with_columns)
    events: list[str] = []
    resolver_calls: list[str] = []
    module = module_factory(
        """
from typing import Any
import polars as pl
from hamilton.function_modifiers import hamilton_exclude, pipe_input, source, step
from hamilton.function_modifiers.delayed import resolve_from_config
from hamilton.plugins.h_polars import with_columns

def seed() -> Any:
    events.append("seed")
    return "unsafe"

def helper(first: pl.Series, second: pl.Series) -> pl.Series:
    events.append("helper")
    return first + second

@pipe_input(step(helper, second=source("seed")).when(mode="unsafe"))
def total(seed: Any) -> pl.Series:
    events.append("total")
    return seed

@hamilton_exclude
def decorate_with():
    resolver_calls.append("resolve")
    return with_columns(
        total,
        columns_to_pass=["left"],
        select=["total"],
        namespace="metrics",
    )

@resolve_from_config(decorate_with=decorate_with)
def enriched(frame: pl.DataFrame) -> pl.DataFrame:
    events.append("enriched")
    return frame
""",
        events=events,
        resolver_calls=resolver_calls,
    )
    driver = Driver(
        module,
        config={settings.ENABLE_POWER_USER_MODE: True, "mode": "unsafe"},
    )
    assert resolver_calls == ["resolve"]
    generated = driver._nodes["metrics.total.with_helper"]
    assert generated.inputs["seed"].requirements == (pl.Series, pl.Series)

    plan = driver.prepare(["enriched"], check_outputs=False)
    with pytest.raises(ExceptionGroup) as failure:
        await plan.execute(inputs={"frame": pl.DataFrame({"left": [3, 5]})})

    assert failure.group_contains(
        TypeError, match="Invalid input for metrics.total.with_helper.seed"
    )
    assert events == ["seed"]
    assert resolver_calls == ["resolve"]
