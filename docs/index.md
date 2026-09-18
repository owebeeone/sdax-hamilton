# Hamilton decorators, SDAX execution

**sdax-hamilton** brings Python SDAX's execution and resource lifecycle features
to graphs written with Hamilton's real decorators. Keep your typed functions and
familiar Hamilton imports. Add `@execution` for per-attempt timeouts and retries
with exponential backoff and jitter, and `@shutdown` for cleanup sequenced in
reverse dependency order.

For supported declarations, Hamilton still resolves configuration, bindings and
decorator expansion. SDAX runs the resulting graph: consumers finish before their
resources close, and dependent resources close before the resources they need.
You describe the dependencies once; you do not write a second shutdown graph.

[Get started](QuickStart.md){ .md-button .md-button--primary }
[Read the API guide](API.md){ .md-button }

## Two extra decorators

| Add to your Hamilton graph | What it provides |
| --- | --- |
| `@execution(timeout=5, retries=2)` | Up to three attempts for retryable failures, with SDAX's backoff and jitter between attempts. |
| `@shutdown(of=resource)` | A cleanup function tied to an acquisition, ordered after its consumers and before its prerequisites are released. |

Both come from `sdax_hamilton`. Continue importing graph decorators such as
`config`, `inject`, `parameterize` and `subdag` from Hamilton itself. Cleanup can
also have its own timeout and retry policy.

```python
from hamilton.function_modifiers import inject, value
from sdax_hamilton import execution


@execution(timeout=5.0, retries=2, initial_delay=0.25, backoff_factor=2.0)
@inject(prefix=value("Hello"))
async def greeting(name: str, prefix: str) -> str:
    return f"{prefix}, {name}"
```

[The quick start](QuickStart.md) adds a resource and its shutdown function to a
complete runnable example. [Retries and shutdown](Lifecycle.md) explains jitter,
cleanup ordering, cancellation and resource scopes.

## Prepare once, run repeatedly

`Driver(nodes).prepare(["greeting"])` compiles a reusable in-memory SDAX plan.
Each invocation has separate values and acquisition records. Use `execute()` for
ordinary results, or `open()` to keep owned results alive while the caller uses
them. The frontend checks declared parameter/result bindings before execution
and checks returned values by default.

## Current compatibility

These pages describe the **0.2.0 alpha** and follow subsequent development on
`main`. The API is experimental and targets Python 3.11–3.13, Hamilton 1.90.0
and SDAX 0.7.2.

Version 0.2.0 covers the documented static decorator families
and bounded optional profiles. It does not provide every Hamilton runtime
feature: cache/Ray decorators retain metadata only, and dynamic graph execution
is outside this scope. See [Compatibility](Compatibility.md) for exact limits.
Timeouts are cooperative, and resource acquisitions with shutdown cannot use
forward retries. These boundaries keep the execution and lifetime promises explicit.
