"""Pinned stock facts for the optional Pandas with_columns surface."""

import os

import pytest

if os.environ.get("SDAX_HAMILTON_TEST_PROFILE") != "pandas":
    pytest.skip("requires SDAX_HAMILTON_TEST_PROFILE=pandas", allow_module_level=True)

import pandas as pd


def test_with_columns_preserves_namespace_config_schema_and_values(hamilton_oracle):
    source = """
import pandas as pd

from hamilton.function_modifiers import config
from hamilton.plugins.h_pandas import with_columns

@config.when(scale=2)
def scaled__two(value: pd.Series) -> pd.Series:
    return value * 2

@config.when(scale=3)
def scaled__three(value: pd.Series) -> pd.Series:
    return value * 3

@with_columns(
    scaled__two,
    scaled__three,
    columns_to_pass=["value"],
    select=["scaled"],
    namespace="features",
    config_required=["scale"],
)
def enriched(frame: pd.DataFrame) -> pd.DataFrame:
    return frame
"""
    oracle = hamilton_oracle(source, config={"scale": 2})

    assert set(oracle.graph.nodes) >= {
        "enriched",
        "features._append",
        "features.scaled",
        "features.value",
    }
    assert oracle.graph.nodes["features.value"].type is pd.Series
    assert oracle.graph.nodes["features._append"].type is pd.DataFrame
    assert oracle.graph.nodes["enriched"].type is pd.DataFrame
    assert oracle.graph.nodes["features.scaled"].tags["hamilton.config"] == "scale"
    assert oracle.graph.nodes["features.scaled"].tags["hamilton.non_final_node"] is True

    frame = pd.DataFrame({"value": [2, 4]})
    result = oracle.execute(["enriched"], inputs={"frame": frame})["enriched"]

    pd.testing.assert_frame_equal(result, pd.DataFrame({"value": [2, 4], "scaled": [4, 8]}))
