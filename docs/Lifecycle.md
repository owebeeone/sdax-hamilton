# Retries, jitter and shutdown sequencing

Import Hamilton's graph decorators from Hamilton as usual. The two declarations
specific to this frontend are `execution` and `shutdown`, imported from
`sdax_hamilton`. They attach policies to the compiled graph; direct calls to the
decorated functions remain ordinary Python calls.

## Retry a call

```python
@execution(
    timeout=5.0,
    retries=3,
    initial_delay=0.5,
    backoff_factor=2.0,
    retryable_exceptions=(ConnectionError, TimeoutError),
)
async def fetch_report(connection: Connection) -> str:
    return await connection.fetch_report()
```

This excerpt allows one initial attempt and up to three additional attempts.
Each attempt has a five-second timeout. Only the selected exception classes
trigger retries; by default those are `ConnectionError`, `TimeoutError` and
`sdax.RetryableException`.

SDAX 0.7.2 supplies the delay and jitter. For retry number `k`, starting at zero,
the delay is:

```text
initial_delay × backoff_factor**k × uniform(0.5, 1.0)
```

With the settings above, successive waits fall between 0.25–0.5 seconds,
0.5–1 second and 1–2 seconds. Jitter varies the retry timing so simultaneous
failures need not produce synchronized retries. There is no separate `jitter=`
argument on these frontend decorators; it is part of the pinned SDAX behavior.

Retry waits sit outside the per-attempt timeout. A timed-out call must finish
draining before the next attempt starts. Timeouts therefore remain cooperative:
blocking synchronous code or code that suppresses cancellation can overrun them.
There is no total-run deadline implied by these settings.

## Release resources in dependency order

```python
@shutdown(of=connection, timeout=2.0)
async def close_connection(acquired: Acquisition[Connection]) -> None:
    if acquired.is_valid:
        await acquired.value.close()
```

The shutdown function receives an `Acquisition[T]` record. It can distinguish
failure before any value was returned, an invalid returned value, and a valid
resource. The [API guide](API.md#acquisition-and-shutdown) defines those cases.

For a graph in which a query uses a transaction and the transaction uses a
connection, shutdown follows these dependencies:

1. Finish or drain the query and any other transaction consumers.
2. Run the transaction's shutdown while its connection is still available.
3. Run the connection's shutdown after its consumers have drained.

SDAX derives this sequence from the forward dependencies and the declared
shutdown associations. Declaration order does not set shutdown order. Unrelated
resources have no guaranteed total order.

`execute()` returns ordinary results after cleanup. `open()` keeps requested
owned results alive through the caller's `async with` body and drains cleanup
on exit, including when the body fails or is cancelled.

## Separate call and cleanup policies

`@execution(...)` governs the forward call. `@shutdown(of=..., ...)` accepts its
own timeout, retry exception set, retry count, initial delay and backoff factor.
They are separate policies, and repeated effects must be safe for your application.

An acquisition with a shutdown cannot currently have forward retries. Acquire
and return the resource first, then perform retryable work in dependent nodes,
as in the [quick start](QuickStart.md). If acquisition fails before returning,
it must clean up any partial work that never reached its acquisition record.

Returned-value validation happens outside the retryable call; a type mismatch
does not rerun a successful effect. Caller cancellation is not a retryable
failure. The runtime retains cleanup work across further caller cancellation and
preserves the primary failure with secondary diagnostics available through
`failures(exc)`.

When a Hamilton decorator expands one declaration into several nodes, use the
explicit `target_` argument where the policy target would otherwise be ambiguous.
See the [policy reference](API.md#execution-policies) and
[compatibility boundaries](Compatibility.md) for admitted combinations.
