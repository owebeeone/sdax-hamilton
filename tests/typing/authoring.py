"""Static authoring contract: run mypy on this file with the package installed."""

from typing import Any, assert_type

from sdax_hamilton import Acquisition, PreparedPlan, execution, shutdown


class Connection:
    def close(self) -> None:
        pass


@execution(timeout=1.0)
def database(name: str) -> Connection:
    return Connection()


@shutdown(of=database, timeout=1.0)
def close_database(state: Acquisition[Connection]) -> None:
    if state.has_value:
        assert_type(state.value, Connection)
        state.value.close()


@execution(timeout=1.0, retries=1)
async def count(database: Connection, *, limit: int = 10) -> int:
    return limit


async def authoring_contract(plan: PreparedPlan, state: Acquisition[Connection]) -> None:
    connection = database("example")
    assert_type(connection, Connection)
    assert_type(close_database(state), None)
    assert_type(await count(connection, limit=4), int)
    assert_type(await plan.execute(inputs={"name": "example"}), dict[str, Any])
    async with plan.open(inputs={"name": "example"}) as values:
        assert_type(values, dict[str, Any])
