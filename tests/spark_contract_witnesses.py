"""Importable primitive and Column witnesses for the local Spark profile."""

from hamilton.plugins.h_spark import require_columns
from pyspark.sql import Column, DataFrame
from pyspark.sql import functions as functions

primitive_driver_calls: list[str] = []


def primitive_double(value: int) -> int:
    """A primitive UDF that can execute only when the caller collects."""
    primitive_driver_calls.append("primitive")
    return value * 2


def executor_sentinel(value: int) -> int:
    """Make accidental Spark action execution visible to the characterization."""
    raise RuntimeError("spark executor sentinel")


@require_columns("value")
def plus_one(value: DataFrame) -> Column:
    """A nested Column transform for ``pass_dataframe_as`` coverage."""
    return value["value"] + functions.lit(1)
