"""Pinned stock facts for the optional experimental parameterize_frame surface."""

import inspect
import os

import pytest

if os.environ.get("SDAX_HAMILTON_TEST_PROFILE") != "pandas":
    pytest.skip("requires SDAX_HAMILTON_TEST_PROFILE=pandas", allow_module_level=True)

import pandas as pd

from sdax_hamilton import Driver
from sdax_hamilton._hamilton_bindings import (
    capture_bindings,
    is_parameterize_extract,
)


def test_parameterize_frame_eagerly_snapshots_rows_names_schema_and_literals(module_factory):
    from hamilton import driver

    specification = pd.DataFrame(
        [["left", "left_double", "seed", 2], ["right", "right_double", "seed", 3]],
        columns=[
            ["left", "left_double", "number", "factor"],
            ["out", "out", "source", "value"],
        ],
    )
    source = """
import pandas as pd

from hamilton.experimental.decorators.parameterize_frame import parameterize_frame

@parameterize_frame(specification)
def columns(number: pd.Series, factor: int) -> pd.DataFrame:
    return pd.DataFrame({"one": number * factor, "two": number * factor * 2})
"""
    module = module_factory(source, specification=specification)
    specification.iloc[0, 2] = "changed_after_decoration"
    oracle = driver.Builder().with_modules(module).build()

    assert set(oracle.graph.nodes) >= {
        "columns__0",
        "columns__1",
        "left",
        "left_double",
        "right",
        "right_double",
        "seed",
    }
    assert oracle.graph.nodes["columns__0"].type is pd.DataFrame
    assert oracle.graph.nodes["left"].type is pd.Series
    assert oracle.graph.nodes["left"].tags["module"] == oracle.graph.nodes["columns__0"].tags[
        "module"
    ]
    assert "changed_after_decoration" not in oracle.graph.nodes

    values = oracle.execute(
        ["left", "left_double", "right", "right_double"],
        inputs={"seed": pd.Series([1, 2])},
    )

    pd.testing.assert_series_equal(values["left"], pd.Series([2, 4], name="left"))
    pd.testing.assert_series_equal(
        values["left_double"], pd.Series([4, 8], name="left_double")
    )
    pd.testing.assert_series_equal(values["right"], pd.Series([3, 6], name="right"))
    pd.testing.assert_series_equal(
        values["right_double"], pd.Series([6, 12], name="right_double")
    )


@pytest.mark.asyncio
async def test_parameterize_frame_reuses_b_contracts_for_defaults_and_projections(
    module_factory, monkeypatch
):
    fallback = pd.Series([5, 7], name="seed")
    specification = pd.DataFrame(
        [["left", "seed", 2]],
        columns=[["left", "number", "factor"], ["out", "source", "value"]],
    )
    module = module_factory(
        """
import pandas as pd

from hamilton.experimental.decorators.parameterize_frame import parameterize_frame

@parameterize_frame(specification)
def columns(
    number: pd.Series,
    seed: pd.Series = fallback,
    factor: int = 1,
) -> pd.DataFrame:
    return pd.DataFrame({"left": number * factor})
""",
        fallback=fallback,
        specification=specification,
    )

    assert is_parameterize_extract(module.columns.expand[0])
    captured = capture_bindings(
        module.columns,
        module.columns.expand[0],
        {"number": pd.Series, "seed": pd.Series, "factor": int, "return": pd.DataFrame},
        inspect.signature(module.columns).parameters,
    )
    binding = captured["columns__0"]["seed"]
    assert binding.default is fallback
    assert binding.requirements == (pd.Series, pd.Series)

    driver = Driver(module)
    spec = driver._nodes["columns__0"].inputs["seed"]
    assert spec.default is fallback
    assert spec.requirements == (pd.Series, pd.Series)
    assert (await driver.prepare(["left"]).execute())["left"].tolist() == [10, 14]


@pytest.mark.asyncio
async def test_parameterize_frame_config_resolution_preserves_synthesized_names(
    module_factory, monkeypatch
):
    specification = pd.DataFrame(
        [["left", "seed"]],
        columns=[["left", "number"], ["out", "source"]],
    )
    module = module_factory(
        """
import pandas as pd

from hamilton.experimental.decorators.parameterize_frame import parameterize_frame
from hamilton.function_modifiers import config

@config.when(mode="one")
@parameterize_frame(specification)
def columns__one(number: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"left": number})
""",
        specification=specification,
    )

    driver = Driver(module, config={"mode": "one"})

    assert driver._nodes["columns__0"].inputs["seed"].requirements == (pd.Series,)
    assert (await driver.prepare(["left"]).execute(inputs={"seed": pd.Series([3, 5])}))[ 
        "left"
    ].tolist() == [3, 5]


@pytest.mark.asyncio
async def test_parameterize_frame_projection_borrows_its_owned_expansion(
    module_factory, monkeypatch
):
    events: list[object] = []
    specification = pd.DataFrame(
        [["left", "seed"]],
        columns=[["left", "number"], ["out", "source"]],
    )
    module = module_factory(
        """
import pandas as pd

from hamilton.experimental.decorators.parameterize_frame import parameterize_frame
from sdax_hamilton import Acquisition, shutdown

@parameterize_frame(specification)
def columns(number: pd.Series) -> pd.DataFrame:
    events.append("acquire")
    return pd.DataFrame({"left": number})

@shutdown(of=columns)
def close(state: Acquisition[pd.DataFrame]) -> None:
    events.append(("release", state.value["left"].tolist()))
""",
        events=events,
        specification=specification,
    )
    driver = Driver(module)

    assert driver._nodes["left"].borrow_from == frozenset({"columns__0"})
    async with driver.prepare(["left"]).open(inputs={"seed": pd.Series([2, 4])}) as result:
        assert result["left"].tolist() == [2, 4]
    assert events == ["acquire", ("release", [2, 4])]
