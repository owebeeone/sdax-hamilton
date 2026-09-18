# API guide

This guide describes the 0.2.0 API. See
[Compatibility](Compatibility.md) for the exact supported declaration subset and
[implementation status](https://github.com/owebeeone/sdax-hamilton/blob/main/dev-docs/Coverage-Execution.md)
for qualification. Start with [Quick Start](QuickStart.md) for a runnable example
or [Retries and shutdown](Lifecycle.md) for the lifecycle guide.

## Driver and prepared plans

`Driver(*modules, config=None)` discovers typed application functions and shutdown
declarations in the supplied Python modules. It uses the installed Hamilton to
resolve admitted decorators, checks declarations and retains a typed node and
ownership representation. SDAX schedules generated calls, including admitted I/O
adapters; Hamilton's scheduler and execution lifecycle adapters are not used.

`driver.prepare(final_vars, *, optional_inputs=(), override_nodes=(),
check_outputs=True)` selects and validates a graph and constructs one SDAX
processor. It returns a reusable `PreparedPlan`.

- `final_vars` names the requested outputs.
- `optional_inputs` declares optional external inputs that will be supplied.
  Undeclared optional inputs use the function defaults.
- `override_nodes` fixes which ordinary computed nodes will instead receive
  caller-supplied values. Their unnecessary upstream work is pruned.
- `check_outputs` enables runtime result validation by default. Acquisition
  records still distinguish raw and type-valid values.

Preparation fixes the graph shape. Each invocation must supply the required
inputs and declared overrides; it cannot silently recompile the plan by changing
that shape. Inputs and overrides are checked before acquisition begins. Config
values, function defaults and admitted Hamilton literal bindings are also checked
against their declared contracts.

```python
from sdax_hamilton import Driver
import nodes

driver = Driver(nodes, config={"mode": "production"})
plan = driver.prepare(["report"])


async def run(customer_id: int):
    return await plan.execute(inputs={"customer_id": customer_id})
```

`await plan.execute(*, inputs=None, overrides=None)` returns a dictionary of the
requested values after cleanup completes. Direct owned-resource outputs are
rejected for this interface. Ordinary results must be safe to use after cleanup.

`async with plan.open(inputs=..., overrides=...) as values` exposes the output
dictionary while resources remain acquired. Exiting the scope drains cleanup,
including when the caller body raises or is cancelled.

A plan reuses its processor in memory and creates fresh context, values and
acquisition records per invocation. There is no disk plan persistence, checkpoint
resume, result cache or resource reuse across invocations. Function globals,
closures, mutable defaults, config objects and bound literal objects are not deep
copied. Their safety under overlapping invocations remains the author's duty.

## Execution policies

Import `execution` and `shutdown` from `sdax_hamilton`. These declarations attach
metadata; they do not change what a direct call to the decorated function does.

Both accept these keyword-only policy arguments:

| Argument | Default | Contract |
|---|---|---|
| `target_` | `None` | Generated node name, or a collection of names copied to an immutable tuple. Required when a declaration expands to multiple candidate nodes. |
| `timeout` | `None` | Positive finite seconds per attempt; `None` disables the timeout. |
| `retries` | `0` | Number of additional attempts; nonnegative integer, excluding booleans. |
| `retryable_exceptions` | `None` | Explicit nonempty tuple of exception classes, or delegate to pinned SDAX's defaults. Cannot include cancellation through a broad superclass. |
| `initial_delay` | `1.0` | Nonnegative finite initial retry delay in seconds. |
| `backoff_factor` | `2.0` | Positive finite retry delay multiplier. |

`@execution(...)` applies the policy to forward execution. `@shutdown(of=fn, ...)`
declares cleanup for the acquisition function `fn` and independently configures
its cleanup attempts. An explicit target selects generated names after Hamilton
configuration and expansion; it is not a new name for the original function.

Pinned SDAX supplies retry execution, delay/backoff and jitter behavior. The
frontend matches its default exception set: `TimeoutError`, `ConnectionError`
and `sdax.RetryableException`. Retry delays are outside
each attempt's timeout; there is no whole-run deadline. A timeout must drain the
cancelled attempt before a retry can begin. A callback that suppresses cancellation
can therefore exceed the timeout: this is cooperative cancellation, not a hard
deadline. Synchronous callbacks run inline and must not block the event loop.

Result validation is outside the retryable forward call. A successful call whose
result fails validation is not repeated merely to satisfy its annotation.
Likewise, rejecting a non-`None` cleanup result does not repeat a completed cleanup.
Actual user exceptions admitted by a retry policy can repeat side effects; the
author must make those effects safe to retry. Acquisitions with shutdown may not
use forward retries until cleanup between attempts has a defined contract.

## Acquisition and shutdown

An acquisition is an ordinary typed function with a matching shutdown declaration.
Shutdown takes exactly one required positional `Acquisition[T]` parameter and
returns `None`. It cannot also carry `execution` or Hamilton decorators.

```python
from sdax_hamilton import Acquisition, execution, shutdown


class Connection:
    async def close(self) -> None:
        pass


@execution(timeout=10.0)
async def database() -> Connection:
    return Connection()


@shutdown(of=database, timeout=5.0)
async def close_database(acquired: Acquisition[Connection]) -> None:
    if acquired.is_valid:
        await acquired.value.close()
    elif acquired.has_value:
        # Handle an invalid raw object only with a defensible recovery contract.
        raise TypeError("database returned a value that cannot safely be closed")
```

For the `database` output, use `driver.prepare(["database"]).open(...)`. Cleanup
is tied to the selected acquisition, not to discovery order. Consumers finish or
drain before their resources are released; dependent resources release before
their prerequisites. There is no guaranteed total order between unrelated nodes.

Shutdown can run even if acquisition failed or was cancelled before returning.
The record makes that distinction explicit:

| Property | Meaning |
|---|---|
| `has_value` | Acquisition returned a raw value. An actual `None` counts as a value. |
| `raw_value` | Returned object without a typed guarantee; raises if no value was returned. |
| `is_valid` | A returned value satisfies the acquisition's declared type. |
| `value` | Typed access only when valid; raises otherwise. |

The runtime records raw returned objects before validating their type, so a
validation failure does not erase a cleanup obligation. This does not make an
arbitrary invalid object safe to clean up. The shutdown author must define any
raw-object recovery path.

Objects allocated and then lost inside a failed acquisition before it returns are
not available through this record. The acquisition must clean up such partial
work itself. Prefer a small acquisition that returns the resource, followed by
separate fallible initialization nodes. There is no public mid-acquisition
publication protocol in this alpha.

Each selected expansion of a declared acquisition must have exactly one shutdown
owner. Runtime overrides and config replacements of owned acquisitions are
rejected. Supported resource extraction projections borrow
their raw acquisition; selecting them retains its cleanup dependency. Shared
resources across runs and arbitrary singleton alias detection are not supported.
The frontend cannot prevent an
ordinary result from secretly retaining a closed resource, or a user-created task
from outliving it. Keep resource use inside the owning scope.

## Failures and cancellation

Ordinary execution and cleanup failures retain their original exception objects
when combined in exception groups. Caller-body exceptions and caller cancellation
remain the original primary object; the frontend first drains cleanup and then
propagates that primary failure. Caller cancellation takes precedence if it arrives
while cleanup is already handling a body exception.

Use `failures(exc)` to inspect attached secondary diagnostics. A cancellation
raised by a cleanup callback is a cleanup diagnostic, distinct from cancellation
of the caller. Further caller cancellation does not abandon the retained cleanup
drain task. This contract remains cooperative: a callback that never yields or
refuses to finish can prevent scope exit.

```python
from sdax_hamilton import failures


async def run(plan):
    try:
        return await plan.execute()
    except BaseException as exc:
        for secondary in failures(exc):
            print(repr(secondary))
        raise
```

This pattern observes cancellation and re-raises it; it does not convert it into a
successful result. The frontend does not add retries around the complete plan.
