# sdax-hamilton

A typed Hamilton frontend for Python SDAX's dependency execution and resource
lifecycle runtime.

Import the real supported Hamilton decorators, then add `execution` policies and
`shutdown` declarations. The frontend compiles Hamilton's resolved graph into one
reusable SDAX plan. Each invocation gets its own values and acquisition records.
SDAX owns scheduling, retries, timeouts and reverse dependency shutdown.

**Status:** initial alpha implementation, version `0.1.0a1`. The API is not frozen.
See the [implementation status](dev-docs/Implementation-Status.md) for validation
and the [compatibility limits](docs/Compatibility.md) before adopting it.

## Install from this checkout

Python 3.11 or later is required. This alpha pins `sdax==0.7.2` and
`apache-hamilton==1.90.0`.

```sh
python -m pip install .
```

Define an application module, for example `nodes.py`:

```python
from hamilton.function_modifiers import inject, value
from sdax_hamilton import execution


@execution(timeout=5.0, retries=2)
@inject(prefix=value("Hello"))
async def greeting(name: str, prefix: str) -> str:
    return f"{prefix}, {name}"
```

Prepare once and execute inside your application's event loop:

```python
import nodes
from sdax_hamilton import Driver

plan = Driver(nodes).prepare(["greeting"])


async def greet(name: str) -> str:
    result = await plan.execute(inputs={"name": name})
    return result["greeting"]
```

Use `plan.open(...)` when a requested result is an owned resource: its lifetime
then includes the caller's `async with` body. See the [API guide](docs/API.md) for
acquisition, cleanup, cancellation and retry contracts.

This is a whole-graph translator, not an adapter for Hamilton's `AsyncDriver`.
The minimal SDAX core API remains unchanged. Declared parameter/result bindings
are checked; this does not prove Python function bodies or give result dictionaries
per-key static types.

## Development

```sh
python -m pip install '.[test]'
python -m ruff check --no-cache src tests examples
python -m mypy src/sdax_hamilton tests/typing/authoring.py
python -m pytest -q -p no:cacheprovider
```

Public tests run from this repository without the workspace, private evidence or
ignored `scratch/` prototypes. The historical
[design and comparison documents](dev-docs/README.md) explain the decisions;
the current API guide describes the implemented surface.

MIT licensed; see [LICENSE](LICENSE).
