# Quick start

This example uses the 0.2.0 alpha. It combines
Hamilton parameter binding, an SDAX retry policy, and an explicit shutdown.
No external service or credentials are needed.

## Install

Use Python 3.11–3.13:

```sh
python -m pip install sdax-hamilton==0.2.0
```

The release pins `apache-hamilton==1.90.0` and `sdax==0.7.2`. See [Compatibility](Compatibility.md) for the supported decorators and optional
profiles. To try subsequent development on `main` in a separate environment:

```sh
python -m pip install 'git+https://github.com/owebeeone/sdax-hamilton.git@main'
```

## Define the graph

Save this as `nodes.py`:

```python
from dataclasses import dataclass

from hamilton.function_modifiers import inject, value
from sdax_hamilton import Acquisition, execution, shutdown


@dataclass
class Connection:
    attempts: int = 0
    closed: bool = False


async def connection() -> Connection:
    print("open connection")
    return Connection()


@shutdown(of=connection, timeout=2.0)
async def close_connection(acquired: Acquisition[Connection]) -> None:
    if acquired.is_valid:
        acquired.value.closed = True
        print("close connection")


@execution(timeout=5.0, retries=2, initial_delay=0.1, backoff_factor=2.0)
@inject(prefix=value("Hello"))
async def greeting(connection: Connection, name: str, prefix: str) -> str:
    assert not connection.closed
    connection.attempts += 1
    print(f"attempt {connection.attempts}")
    if connection.attempts == 1:
        raise ConnectionError("simulated temporary failure")
    return f"{prefix}, {name}"
```

Hamilton's `@inject` supplies the prefix. `@execution` gives the greeting up to
two retries, while the connection stays live. `@shutdown` associates cleanup with
the connection. The acquisition itself has no retries: it must return its resource
before fallible retryable work begins.

## Prepare and execute

Save this alongside it as `run.py`:

```python
import asyncio

import nodes
from sdax_hamilton import Driver

plan = Driver(nodes).prepare(["greeting"])


async def main() -> None:
    result = await plan.execute(inputs={"name": "Ada"})
    print(result["greeting"])


if __name__ == "__main__":
    asyncio.run(main())
```

```sh
python run.py
```

Expected output:

```text
open connection
attempt 1
attempt 2
close connection
Hello, Ada
```

The greeting retries after a short jittered delay. Cleanup completes before
`execute()` returns. Reuse `plan` for subsequent invocations; each run acquires
its own connection and has its own attempt state.

## Keep an owned result open

When the caller needs the resource itself, use an explicit lifetime scope:

```python
resource_plan = Driver(nodes).prepare(["connection"])


async def use_connection() -> None:
    async with resource_plan.open() as values:
        connection = values["connection"]
        assert not connection.closed
        # Use the connection here.
    assert connection.closed
```

`open()` drains cleanup when the scope exits, including on exceptions or caller
cancellation. See [Retries and shutdown](Lifecycle.md) for sequencing and failure
contracts, and [API guide](API.md) for generated-node targets and checked bindings.
