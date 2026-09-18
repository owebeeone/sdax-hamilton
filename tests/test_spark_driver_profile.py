"""Opt-in public Driver tests for caller-owned, lazy local Spark plans."""

# ruff: noqa: E402

import os
import sys

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

from hamilton.function_modifiers import subdag
from hamilton.plugins import h_spark
from pyspark import SparkContext
from pyspark.sql import Column, DataFrame, SparkSession

from sdax_hamilton import Acquisition, Driver, execution, shutdown


def _assert_no_active_jobs(spark_session: SparkSession) -> None:
    assert spark_session.sparkContext.statusTracker().getActiveJobsIds() == []


@pytest.fixture
def spark_session(monkeypatch):
    """Create and finally stop the one caller-owned local Spark session."""
    if SparkContext._active_spark_context is not None:
        pytest.fail("G3 frontend qualification requires no pre-existing SparkContext")
    monkeypatch.setenv("PYARROW_IGNORE_TIMEZONE", "1")
    monkeypatch.setenv("SPARK_LOCAL_IP", "127.0.0.1")
    monkeypatch.setenv("PYSPARK_PYTHON", sys.executable)
    session = (
        SparkSession.builder.master("local[2]")
        .appName("sdax-hamilton-g3-frontend")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    try:
        yield session
    finally:
        session.stop()


@pytest.mark.asyncio
async def test_driver_returns_a_lazy_caller_owned_spark_dataframe(
    module_factory, monkeypatch, spark_session
):
    """SDAX prepares the stock lazy plan; only the test performs an action."""
    calls: list[str] = []

    module = module_factory(
        """
def primitive_double(value: int) -> int:
    return value * 2

@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
    config_required=["enabled"],
)
def enriched(frame: DataFrame) -> DataFrame:
    calls.append("outer")
    return frame
""",
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
        calls=calls,
    )

    driver = Driver(module, config={"enabled": True})
    assert set(driver._nodes) == {
        "enriched",
        "enriched.primitive_double",
        "primitive_double",
    }
    assert calls == []
    _assert_no_active_jobs(spark_session)
    raw = spark_session.createDataFrame([(1,), (2,)], ["value"])

    result = await driver.prepare(["enriched"]).execute(inputs={"frame": raw})
    transformed = result["enriched"]

    assert transformed.columns == ["value", "primitive_double"]
    assert calls == ["outer"]
    assert SparkContext._active_spark_context is spark_session.sparkContext
    _assert_no_active_jobs(spark_session)
    assert sorted((row.asDict() for row in transformed.collect()), key=lambda row: row["value"]) == [
        {"value": 1, "primitive_double": 2},
        {"value": 2, "primitive_double": 4},
    ]


@pytest.mark.asyncio
async def test_driver_allows_require_columns_only_inside_the_copied_spark_subdag(
    module_factory, monkeypatch, spark_session
):
    """The nested Column helper remains part of the caller-owned lazy chain."""
    module = module_factory(
        """
@require_columns("value")
def _plus_one(value: DataFrame) -> Column:
    return value["value"] + 1

@select(
    _plus_one,
    pass_dataframe_as="value",
    output_cols=["_plus_one"],
    namespace="nested",
)
def nested(value: DataFrame) -> DataFrame:
    return value
""",
        require_columns=h_spark.require_columns,
        select=h_spark.select,
        with_columns=h_spark.with_columns,
        Column=Column,
        DataFrame=DataFrame,
    )

    driver = Driver(module)
    raw = spark_session.createDataFrame([(1,), (2,)], ["value"])
    transformed = (await driver.prepare(["nested"]).execute(inputs={"value": raw}))["nested"]

    assert transformed.columns == ["_plus_one"]
    _assert_no_active_jobs(spark_session)
    assert sorted((row.asDict() for row in transformed.collect()), key=lambda row: row["_plus_one"]) == [
        {"_plus_one": 2},
        {"_plus_one": 3},
    ]


def test_driver_rejects_standalone_require_columns(module_factory, monkeypatch):
    """The exact Spark profile does not admit top-level Column transformations."""
    module = module_factory(
        """
@require_columns("value")
def direct(frame: DataFrame) -> Column:
    raise AssertionError("construction must not call direct")
""",
        require_columns=h_spark.require_columns,
        Column=Column,
        DataFrame=DataFrame,
    )

    with pytest.raises(ValueError, match="direct: standalone Spark require_columns is unsupported"):
        Driver(module)
    assert SparkContext._active_spark_context is None


def test_driver_rejects_spark_columns_nested_in_a_subdag(module_factory, monkeypatch):
    """Namespaced subdag expansion has no admitted Spark capture contract yet."""
    nested = module_factory(
        """
def primitive_double(value: int) -> int:
    return value * 2

@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
)
def enriched(frame: DataFrame) -> DataFrame:
    raise AssertionError("construction must not call nested Spark declaration")
""",
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
    )
    root = module_factory(
        """
@subdag(nested, namespace="mounted")
def result(enriched: DataFrame) -> DataFrame:
    return enriched
""",
        nested=nested,
        subdag=subdag,
        DataFrame=DataFrame,
    )

    with pytest.raises(
        ValueError, match="enriched: Spark with_columns/select cannot be nested in a Hamilton subdag"
    ):
        Driver(root)
    assert SparkContext._active_spark_context is None


def test_driver_rejects_owned_spark_ancestor_before_callbacks(module_factory, monkeypatch):
    """An acquisition feeding the lazy chain cannot escape SDAX lifetime control."""
    events: list[str] = []
    module = module_factory(
        """
def primitive_double(value: int) -> int:
    return value * 2

def frame() -> DataFrame:
    events.append("acquire")
    raise AssertionError("construction must not acquire")

@shutdown(of=frame)
def close_frame(value: Acquisition[DataFrame]) -> None:
    events.append("release")

@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
)
def enriched(frame: DataFrame) -> DataFrame:
    events.append("outer")
    return frame
""",
        Acquisition=Acquisition,
        shutdown=shutdown,
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
        events=events,
    )

    with pytest.raises(ValueError, match="frame: Spark plan cannot include an owned acquisition"):
        Driver(module)
    assert events == []
    assert SparkContext._active_spark_context is None


def test_driver_rejects_nondefault_policy_on_spark_plan_before_callbacks(
    module_factory, monkeypatch
):
    """Execution policies cannot govern a caller-owned lazy Spark plan."""
    events: list[str] = []
    module = module_factory(
        """
def primitive_double(value: int) -> int:
    return value * 2

@execution(timeout=1)
@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
)
def enriched(frame: DataFrame) -> DataFrame:
    events.append("outer")
    return frame
""",
        execution=execution,
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
        events=events,
    )

    with pytest.raises(ValueError, match="enriched: Spark plan cannot include a nondefault policy"):
        Driver(module)
    assert events == []
    assert SparkContext._active_spark_context is None


@pytest.mark.parametrize(
    ("nested_declaration", "message"),
    (
        (
            """
@execution(timeout=1)
def primitive_double(value: int) -> int:
    return value * 2
""",
            "primitive_double: Spark nested UDF cannot declare an execution policy",
        ),
        (
            """
def primitive_double(value: int) -> int:
    return value * 2

@shutdown(of=primitive_double)
def close_primitive(value: Acquisition[int]) -> None:
    events.append("release")
""",
            "primitive_double: Spark nested UDF cannot declare a shutdown",
        ),
    ),
)
def test_driver_rejects_lifecycle_on_nested_spark_udf_before_expansion(
    module_factory, monkeypatch, nested_declaration, message
):
    """Nested UDF lifecycle state is rejected before Spark can combine it."""
    events: list[str] = []
    module = module_factory(
        nested_declaration
        + """
@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
)
def enriched(frame: DataFrame) -> DataFrame:
    events.append("outer")
    return frame
""",
        Acquisition=Acquisition,
        execution=execution,
        shutdown=shutdown,
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
        events=events,
    )

    with pytest.raises(ValueError, match=message):
        Driver(module)
    assert events == []
    assert SparkContext._active_spark_context is None


@pytest.mark.parametrize("placement", ["loader", "saver", "indirect_saver", "independent"])
def test_spark_rejects_connected_io_before_adapter_construction(
    module_factory, monkeypatch, placement
):
    from dataclasses import dataclass

    from hamilton.io.data_adapters import DataLoader, DataSaver
    from hamilton.registry import LOADER_REGISTRY, SAVER_REGISTRY

    effects = []

    @dataclass
    class Loader(DataLoader):
        @classmethod
        def applicable_types(cls):
            return [DataFrame]

        @classmethod
        def name(cls):
            return "sdax_spark_boundary"

        def __post_init__(self):
            effects.append("loader construction")

        def load_data(self, type_):
            raise AssertionError("must not load during construction")

    @dataclass
    class Saver(DataSaver):
        @classmethod
        def applicable_types(cls):
            return [DataFrame]

        @classmethod
        def name(cls):
            return "sdax_spark_boundary"

        def __post_init__(self):
            effects.append("saver construction")

        def save_data(self, data):
            raise AssertionError("must not save during construction")

    monkeypatch.setitem(LOADER_REGISTRY, Loader.name(), [Loader])
    monkeypatch.setitem(SAVER_REGISTRY, Saver.name(), [Saver])
    prefix = "from hamilton.function_modifiers import load_from, save_to\n"
    if placement in ("loader", "independent"):
        loaded_name = "frame" if placement == "loader" else "unrelated"
        prefix += f"""
@load_from.sdax_spark_boundary()
def {loaded_name}(loaded: DataFrame) -> DataFrame:
    return loaded
"""
    saver = "@save_to.sdax_spark_boundary(output_name_='sink')\n"
    policy = "@execution(target_='sink', timeout=1)\n"
    outer = policy + saver if placement == "saver" else ""
    suffix = ""
    if placement == "indirect_saver":
        suffix = policy + saver + """
def forwarded(enriched: DataFrame) -> DataFrame:
    return enriched
"""
    elif placement == "independent":
        suffix = saver + """
def unrelated_sink(independent: DataFrame) -> DataFrame:
    return independent
"""
    module = module_factory(
        prefix + """
def primitive_double(value: int) -> int:
    return value * 2
""" + outer + """
@with_columns(primitive_double, columns_to_pass=["value"],
              select=["primitive_double"], namespace="enriched")
def enriched(frame: DataFrame) -> DataFrame:
    return frame
""" + suffix,
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
        execution=execution,
    )
    if placement == "independent":
        Driver(module)
    else:
        with pytest.raises(ValueError, match="Spark plans cannot compose Hamilton I/O decorators"):
            Driver(module)
    assert effects == []
    assert SparkContext._active_spark_context is None


def test_spark_rejects_nested_io_before_native_udf_combination(module_factory):
    module = module_factory(
        '''
from hamilton.function_modifiers import dataloader

@dataloader()
def _loaded_column() -> tuple[int, dict]:
    raise AssertionError("must not load during construction")

@with_columns(_loaded_column, columns_to_pass=["value"],
              select=["_loaded_column"], namespace="enriched")
def enriched(frame: DataFrame) -> DataFrame:
    return frame
''',
        with_columns=h_spark.with_columns,
        DataFrame=DataFrame,
    )
    with pytest.raises(ValueError, match="Spark plans cannot compose Hamilton I/O decorators"):
        Driver(module)
    assert SparkContext._active_spark_context is None
