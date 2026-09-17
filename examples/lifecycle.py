"""Run with ``python examples/lifecycle.py`` after installing sdax-hamilton.

A resource remains live through consumers and is released before execute returns.
For direct resource access use the prepared plan's open() context instead.
"""

import asyncio
import sys
from dataclasses import dataclass

from sdax_hamilton import Acquisition, Driver, execution, shutdown


@dataclass
class Connection:
    name: str
    live: bool = True
    calls: int = 0


async def database(database_name: str) -> Connection:
    print(f"open {database_name}")
    return Connection(database_name)


@shutdown(of=database, timeout=1.0)
async def close_database(state: Acquisition[Connection]) -> None:
    if state.has_value:
        database = state.value
        database.live = False
        print(f"close {database.name}")


@execution(timeout=1.0, retries=1, initial_delay=0)
async def customer_count(database: Connection) -> int:
    assert database.live
    database.calls += 1
    if database.calls == 1:
        raise ConnectionError("temporary query failure")
    return 42


async def _main() -> None:
    driver = Driver(sys.modules[__name__])
    plan = driver.prepare(["customer_count"])
    for name in ("first", "second"):
        print(await plan.execute(inputs={"database_name": name}))
    async with driver.prepare(["database"]).open(inputs={"database_name": "scoped"}) as values:
        assert values["database"].live
        print(f"using {values['database'].name} inside its scope")


if __name__ == "__main__":
    asyncio.run(_main())
