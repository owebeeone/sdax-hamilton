"""Stock Hamilton Spark 4 local-profile characterizations for later G3 admission.

These tests run only when ``SDAX_HAMILTON_TEST_PROFILE=spark`` selects the
explicit optional profile. They exercise a caller-owned ``local[2]`` Spark
session and stock Hamilton. They build lazy DataFrame plans; each transformed
DataFrame is materialized only by the explicit ``collect`` calls in its test.
They do not admit Spark decorators to SDAX.
"""

# ruff: noqa: E402

import os
import sys
from pathlib import Path
from types import MethodType

import pytest

if os.environ.get("SDAX_HAMILTON_TEST_PROFILE") != "spark":
    pytest.skip("requires the explicit Spark test profile", allow_module_level=True)

import pandas
import pyarrow
import pyspark

if (pyspark.__version__, pandas.__version__, pyarrow.__version__) != ("4.0.1", "2.3.3", "21.0.0"):
    raise RuntimeError(
        "Spark profile requires pyspark==4.0.1, pandas==2.3.3, and pyarrow==21.0.0"
    )

from hamilton import driver as hamilton_driver
from hamilton.function_modifiers import base
from hamilton.plugins import h_spark
from pyspark import SparkContext
from pyspark.sql import Column, DataFrame, SparkSession
from spark_contract_witnesses import (
    executor_sentinel,
    plus_one,
    primitive_double,
    primitive_driver_calls,
)


def _stock_driver(module_factory, source: str, *, config=None, **bindings):
    module = module_factory(source, **bindings)
    return hamilton_driver.Builder().with_modules(module).with_config(dict(config or {})).build()


def _counted_stock_driver(module_factory, source: str, *, config=None, **bindings):
    """Build once while counting the ephemeral stock ``with_columns`` expansion."""
    module = module_factory(source, **bindings)
    modifier = module.enriched.inject[0]
    assert type(modifier) is h_spark.with_columns
    original_inject_nodes = modifier.inject_nodes
    calls: list[tuple[object, object, object]] = []

    def counted_inject_nodes(_self, params, configuration, fn):
        calls.append((params, configuration, fn))
        return original_inject_nodes(params, configuration, fn)

    modifier.inject_nodes = MethodType(counted_inject_nodes, modifier)
    stock = hamilton_driver.Builder().with_modules(module).with_config(dict(config or {})).build()
    return stock, calls


def _assert_no_active_jobs(spark_session) -> None:
    assert spark_session.sparkContext.statusTracker().getActiveJobsIds() == []


@pytest.fixture
def spark_session(monkeypatch):
    """Create and stop the one caller-owned local session for each test."""
    if SparkContext._active_spark_context is not None:
        pytest.fail("G3 characterization requires no pre-existing SparkContext")
    monkeypatch.setenv("PYARROW_IGNORE_TIMEZONE", "1")
    monkeypatch.setenv("SPARK_LOCAL_IP", "127.0.0.1")
    monkeypatch.setenv("PYSPARK_PYTHON", sys.executable)
    session = (
        SparkSession.builder.master("local[2]")
        .appName("sdax-hamilton-g3-characterization")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        # Executors need the public witness module independently of pytest's
        # driver-side sys.path adjustments.
        session.sparkContext.addPyFile(str(Path(__file__).with_name("spark_contract_witnesses.py")))
        yield session
    finally:
        session.stop()


def test_explicit_spark_plugin_import_does_not_create_a_session():
    """The G3 profile is opt-in; plugin import alone has no Spark session effect."""
    assert h_spark.with_columns is not None
    assert SparkContext._active_spark_context is None


def test_with_columns_builds_a_lazy_primitive_udf_plan_then_collects_explicitly(
    module_factory, spark_session
):
    construction_events: list[str] = []
    primitive_driver_calls.clear()
    stock, inject_calls = _counted_stock_driver(
        module_factory,
        """
@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
    config_required=["enabled"],
)
def enriched(frame: DataFrame) -> DataFrame:
    construction_events.append("outer")
    return frame
""",
        config={"enabled": True},
        with_columns=h_spark.with_columns,
        primitive_double=primitive_double,
        construction_events=construction_events,
        DataFrame=DataFrame,
    )
    names = {entry.name for entry in stock.list_available_variables()}
    assert names == {"enabled", "enriched", "enriched.primitive_double", "frame"}
    assert len(inject_calls) == 1
    assert construction_events == []
    assert primitive_driver_calls == []
    _assert_no_active_jobs(spark_session)
    raw = spark_session.createDataFrame([(1,), (2,)], ["value"])

    transformed = stock.execute(["enriched"], inputs={"frame": raw})["enriched"]

    assert transformed.columns == ["value", "primitive_double"]
    assert SparkContext._active_spark_context is spark_session.sparkContext
    assert construction_events == ["outer"]
    assert primitive_driver_calls == []
    _assert_no_active_jobs(spark_session)
    assert sorted((row.asDict() for row in transformed.collect()), key=lambda row: row["value"]) == [
        {"value": 1, "primitive_double": 2},
        {"value": 2, "primitive_double": 4},
    ]


def test_nested_require_columns_and_select_keep_the_caller_dataframe_lazy(
    module_factory, spark_session
):
    stock = _stock_driver(
        module_factory,
        """
@with_columns(
    plus_one,
    pass_dataframe_as="value",
    select=["plus_one"],
    namespace="nested",
)
def nested(value: DataFrame) -> DataFrame:
    return value

@select(
    plus_one,
    pass_dataframe_as="value",
    output_cols=["plus_one"],
    namespace="selected",
)
def selected(value: DataFrame) -> DataFrame:
    return value
""",
        with_columns=h_spark.with_columns,
        select=h_spark.select,
        plus_one=plus_one,
        DataFrame=DataFrame,
    )
    names = {entry.name for entry in stock.list_available_variables()}
    assert names == {
        "nested",
        "nested.plus_one",
        "selected",
        "selected.plus_one",
        "selected._select",
        "value",
    }
    raw = spark_session.createDataFrame([(1,), (2,)], ["value"])

    nested = stock.execute(["nested"], inputs={"value": raw})["nested"]
    selected = stock.execute(["selected"], inputs={"value": raw})["selected"]

    assert nested.columns == ["value", "plus_one"]
    assert selected.columns == ["plus_one"]
    _assert_no_active_jobs(spark_session)
    assert sorted((row.asDict() for row in nested.collect()), key=lambda row: row["value"]) == [
        {"value": 1, "plus_one": 2},
        {"value": 2, "plus_one": 3},
    ]
    assert sorted((row.asDict() for row in selected.collect()), key=lambda row: row["plus_one"]) == [
        {"plus_one": 2},
        {"plus_one": 3},
    ]


def test_primitive_udf_sentinel_fires_only_on_the_explicit_collect(module_factory, spark_session):
    stock = _stock_driver(
        module_factory,
        """
@with_columns(executor_sentinel, columns_to_pass=["value"], namespace="sentinel")
def sentinel(frame: DataFrame) -> DataFrame:
    return frame
""",
        with_columns=h_spark.with_columns,
        executor_sentinel=executor_sentinel,
        DataFrame=DataFrame,
    )
    raw = spark_session.createDataFrame([(1,)], ["value"])

    transformed = stock.execute(["sentinel"], inputs={"frame": raw})["sentinel"]

    _assert_no_active_jobs(spark_session)
    with pytest.raises(Exception, match="spark executor sentinel"):
        transformed.collect()


def test_stock_boundary_rejections_and_direct_require_columns_characterization(module_factory):
    with pytest.raises(NotImplementedError, match="on_input"):
        h_spark.with_columns(primitive_double, on_input="frame")
    with pytest.raises(ValueError, match="No dataframe parameters"):
        h_spark.derive_dataframe_parameter({"count": int}, None, "zero")
    with pytest.raises(ValueError, match="More than one dataframe parameter"):
        h_spark.derive_dataframe_parameter(
            {"left": DataFrame, "right": DataFrame}, None, "multiple"
        )
    assert (
        h_spark.derive_dataframe_parameter(
            {"left": DataFrame, "right": DataFrame}, "right", "multiple"
        )
        == "right"
    )

    def direct(value: DataFrame) -> Column:
        return value["value"]

    direct.__name__ = "direct"
    direct_nodes = tuple(base.resolve_nodes(h_spark.require_columns("value")(direct), {}))
    assert direct_nodes[0].tags["hamilton.spark.columns"] == ("value",)
    assert direct_nodes[0].tags["hamilton.spark.target"] == "value"
    # Stock permits this transformation. A later G3 activation must reject this
    # standalone shape; only the nested `with_columns` form is in profile.
