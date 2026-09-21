# API design

Date: 18 September 2026. Status: initial proposal, not an implemented API.

## 1. Purpose and responsibility

Provide declarative, checked parameter/result passing and explicit lifecycle
policy over the existing Python SDAX API. The frontend owns correctness of the
declared connections and generated context bindings. SDAX owns scheduling,
phase transitions, retries, timeouts and cleanup execution.

```text
Hamilton functions and decorators + sdax_hamilton declarations
    → Hamilton graph construction and declared edge-type checking
    → frontend validation, output selection and policy resolution
    → prepared SDAX processor and immutable binding specifications
    → fresh per-run context, results and acquisition state
```

This is a graph translator with a driver-shaped public interface. It does not
plug a callback into Hamilton's `AsyncDriver` and retain Hamilton's execution
machinery. The probe used Hamilton's public Builder for graph construction, then
accessed `Driver.graph`, `get_upstream_nodes`, node callables and input validation.
Those latter interfaces require a versioned compatibility boundary.

All SDAX imports must use its existing public authoring/execution surface. Any
proposed core change requires a concrete execution need that cannot be expressed
by generated callbacks and context. Convenience for this frontend is insufficient.

## 2. Proposed user surface

The following is illustrative authoring syntax. `Connection`, `Customer`,
`TemporaryReadError`, and `connect` belong to the application.

```python
from hamilton.function_modifiers import inject, value
from sdax_hamilton import Acquisition, execution, shutdown


@execution(timeout=5.0)
async def database(dsn: str) -> Connection:
    return await connect(dsn)


@shutdown(of=database, timeout=3.0)
async def close_database(state: Acquisition[Connection]) -> None:
    if state.has_value:
        await state.value.close()


@execution(
    timeout=2.0,
    retries=2,
    retryable_exceptions=(TemporaryReadError,),
    initial_delay=0.1,
    backoff_factor=2.0,
)
@inject(limit=value(100))
async def customers(database: Connection, limit: int) -> list[Customer]:
    return await database.fetch_customers(limit)
```

Hamilton decorators retain their actual imports and signatures. The new decorators
attach declarations; calling a decorated function directly remains an ordinary
Python call and does not acquire orchestration behavior.

`shutdown` registers a release declaration and excludes its function from ordinary
Hamilton computation-node discovery. Registering shutdown associates ownership
with the selected acquisition node. Module discovery must find such declarations
without an application-wide mutable registry or import-order-dependent behavior.
The probe's manually supplied registry is not the final registration API.

### Execution policy

Proposed signature:

```python
execution(
    *,
    target_=None,
    timeout=None,
    retries=0,
    retryable_exceptions=None,
    initial_delay=1.0,
    backoff_factor=2.0,
)
```

| Argument | Proposed contract |
|---|---|
| `target_` | One generated node name or a collection of names. Omission is accepted only when the target is unambiguous. |
| `timeout` | Per-attempt timeout in seconds; `None` means no timeout. Includes resolving the generated callable's result. |
| `retries` | Additional attempts after the first; `2` permits at most three attempts. |
| `retryable_exceptions` | Exception classes eligible for retry. `None` delegates to the supported SDAX version's defaults, which must be documented and tested. |
| `initial_delay`, `backoff_factor` | Delegate delay/backoff behavior, including its jitter, to SDAX. Do not implement a second retry loop. |

Backoff is outside the callback's per-attempt timeout. A total deadline for the
complete operation is a separate, deferred policy; `timeout` must not imply it.
External cancellation must propagate under SDAX's cancellation contract. Reject
retry configurations that would treat external cancellation as an ordinary retry.

Sync callables execute directly unless a separately specified offload facility
is introduced. Timeouts cannot forcibly stop a blocking sync callable. They
initiate cancellation of cooperative async work and may exceed their nominal
duration while cancellation is handled. Documentation must avoid hard-deadline claims.

Plain callbacks use `task_func`. If explicit child-task authoring is introduced,
the frontend must bind SDAX's owned scope through `task_group_func`. Arbitrary
user-created tasks are not automatically adopted. The child-scope API is deferred.

### Shutdown declaration

Proposed signature:

```python
shutdown(
    *,
    of,
    target_=None,
    timeout=None,
    retries=0,
    retryable_exceptions=None,
    initial_delay=1.0,
    backoff_factor=2.0,
)
```

`of` refers to the acquisition function. `target_` disambiguates generated nodes
after Hamilton expansion. The initial shutdown function shape is exactly one
`Acquisition[T]` argument and a `None` return annotation, with sync and async
implementations accepted. Supporting additional injected shutdown dependencies
requires explicit lifetime-edge construction and is deferred.

Preparation verifies that the shutdown's `T` is compatible with the selected
node's output type. Duplicate shutdown ownership, missing targets and ambiguous
targets fail preparation. Shutdown timeout and retry settings are independent
of acquisition settings. Release retries default to zero and require explicit
opt-in; the author is responsible for a release operation that can safely repeat.

Shutdown becomes `post_execute` on the generated acquisition task. It is eligible
when acquisition started, including failure or cancellation. Successful consumers
must finish, and cancelled consumers must stop under the core's contract, before
their required resource is released. Parent resources remain alive through child
release; the frontend does not independently sort or invoke a shutdown list.

## 3. Acquisition state and ownership

`Acquisition[T]` is a frontend-owned, read-only view provided to shutdown:

- `has_value: bool` indicates that a value was published into the ownership record.
- `value: T` returns that value, or raises a documented error if absent.
- A successfully published `None` is distinct from an absent value when `T`
  permits `None`; do not use `None` as the internal missing-value sentinel.

Record a returned resource before output validation or downstream execution.
An output-type validation failure must not discard its cleanup obligation.
The record is unique to one acquisition node in one invocation; no state lives
on the shared prepared plan.

### Partial acquisition: explicit open issue

A wrapper cannot discover a handle acquired inside a function that fails before
returning it. Invoking shutdown with `has_value=False` does not solve that problem.
The first constrained use case is a small acquisition function that returns its
resource before fallible dependent initialization runs in separate graph nodes.
Its own partial-failure contract must still be explicit.

A richer frontend publication/state protocol is a design prerequisite for
supporting arbitrary multi-stage acquisition. It must use existing SDAX context
and callbacks, preserve typed bindings, and make intermediate owned values
available to shutdown. No concrete publication API is chosen in this draft.

Initially reject nonzero acquisition retries for nodes owning resources. A final
shutdown phase is not cleanup between attempts. Enabling acquisition retries
requires an explicit attempt-cleanup protocol and dedicated failure tests.

### Overrides, outputs and aliasing

Reject overrides of owned resource nodes until borrowed-versus-owned semantics
are designed. Ordinary values may be overridden under the prepared shape.

Use a scoped `open()` operation to expose resources while they are alive.
`execute()` completes cleanup before returning ordinary results and rejects
directly requesting owned resource nodes. Neither rule proves that an ordinary
result contains no alias to a resource. Document the lifetime requirement;
do not claim static ownership checking or deep-copy arbitrary Python objects.

Resources retained across multiple invocations are a different ownership scope
and are outside the initial design.

## 4. Preparation and repeated execution

Proposed use:

```python
from sdax_hamilton import Driver
import application_nodes

driver = Driver({}, application_nodes)
plan = driver.prepare(["customers"])

first = await plan.execute(inputs={"dsn": first_dsn})
second = await plan.execute(inputs={"dsn": second_dsn})

resource_plan = driver.prepare(["database"])
async with resource_plan.open(inputs={"dsn": first_dsn}) as values:
    await use_connection(values["database"])
```

Proposed preparation controls:

```python
driver.prepare(
    final_vars,
    *,
    optional_inputs=(),
    override_nodes=(),
    check_outputs=False,
)
```

Preparation builds the selected graph, validates declared types and policies,
and constructs one reusable SDAX processor. Required input names and their types
come from the selected graph. `optional_inputs` declares optional external inputs
present in this shape; absent optional inputs retain Python function defaults.
`override_nodes` identifies nodes replaced by runtime values and prunes their
upstream work when it is no longer needed.

`plan.execute(inputs=..., overrides=...)` and `plan.open(...)` validate runtime
values against the prepared binding contract before acquisition. A supplied
optional-input or override shape that differs from preparation is rejected;
it must not silently rebuild a different graph. Final outputs are fixed by the
plan. Exact naming and treatment of unused input keys remain API-review items.

| Lifetime | Contents |
|---|---|
| Driver | Constructed Hamilton graph, graph-affecting configuration snapshot and discovered declarations. |
| Prepared plan | Selected graph, frozen policy/binding specifications and reusable SDAX processor. |
| Invocation | Fresh value context, acquisition records, phase runner, failures and result mapping. |

Changing input values does not rebuild the plan. Changing graph configuration,
requested outputs, override names or relevant optional-input presence may require
a different plan. Callbacks must not capture an invocation's input values or
mutable state. Concurrent executions may share the plan, not their contexts.
User-supplied mutable objects are not magically isolated by separate contexts.

Start with explicit preparation. A later convenience `Driver.execute()` may use
a bounded cache keyed by graph generation, selected execution shape and policy
options, never by ordinary input values. Cache size, eviction, concurrent cache
misses and configuration invalidation need explicit tests before that API ships.

Persistence here means in-memory reuse. No disk serialization, checkpoints,
cross-process recovery or retained result/resource cache is implied.

## 5. Compilation and validation

1. Discover declarations, excluding registered shutdown functions from Hamilton
   forward-node discovery. Preserve callable signatures for Python tooling.
2. Construct Hamilton's graph using its actual supported function modifiers.
3. Resolve selected outputs, optional inputs and override nodes. Validate
   declared producer/consumer compatibility and target names.
4. Resolve policies against generated node identities. Copy declarations into
   frontend-owned immutable specifications; retain origin information for errors.
5. Build context slots and argument bindings. Omit absent optional arguments.
   Resolve generated callable results according to the resolved-value contract.
6. Generate dependency-ordered SDAX `pre_execute` callbacks and resource
   `post_execute` callbacks. Leave the shared `execute` phase empty for this
   finite-dataflow translation. Build and validate the SDAX processor once.
7. At invocation, validate values and allocate context; execute through the
   existing public SDAX processor/phase-runner API.

The frontend guarantees validation of supported declared connections. It cannot
prove that a function body obeys its annotations. `check_outputs=True` adds
runtime output checking. The initial result mapping is dynamically keyed;
fully statically inferred `execute()` result types are not promised.

Hamilton's current input validator accepts `None` permissively. Proposed frontend
behavior is to accept `None` only when permitted by the declared input type;
this deliberate tightening must be documented and tested. Rules for `Any`,
unions, protocols and parameterized containers need a stated support matrix.

Intentional awaitables-as-data are outside the initial resolved-value contract.
Reject identifiable unsupported annotations/configurations; do not silently turn
such values into different types. This does not imply that dynamic Python code
can always be classified statically.

## 6. Decorator and execution compatibility

An exact decorator name/signature is obtained by using the real Hamilton object.
Compatibility still requires tests of generated names, dependencies, defaults,
configuration, outputs and supported decorator combinations. A compatible
declaration does not imply every Hamilton execution adapter is supported.

| Feature | Initial direction |
|---|---|
| Typed functions, `source`, `value`, `group`, `inject`, `parameterize*` | Initial static-dataflow subset; promote only tested variants. |
| `extract_fields`, `unpack_fields`, `extract_columns` | Initial subset, subject to declared output types and tested library versions. |
| `config.when*`, metadata tags, `subdag`, `parameterized_subdag` | Add conformance coverage; config selection and subgraph expansion occur before execution. Ordinary subgraph success does not establish resource-mount ownership. |
| `does`, `pipe_input`, `check_output*`, `resolve*` | Candidate subset; preserve modifier-specific restrictions and test sync/async behavior. |
| Async `pipe_output` and `mutate` | Gate on a verified Hamilton correction or reject the affected forms with a useful error. No silent global monkey patch. |
| Runtime `Parallelizable` / `Collect` | Reject initially. A separate nested-plan design would need cancellation, ownership and aggregation semantics. |
| Cache execution and arbitrary lifecycle adapters | Not inherited by graph translation. Reject unsupported integration options; metadata alone must not promise caching behavior. |
| Remote executors and specialized dataframe execution | Separate integrations, not automatically supplied by SDAX. |
| I/O decorators/materializer APIs | Future conformance work; ordinary I/O nodes can be executable, but materializer graph preparation and side-effect selection require tests. |
| Resource overrides, acquisition retries, cross-run resources | Reject until their ownership contracts exist. |

Not every spelling in a family above was exercised by the feasibility probe.
The published support list must enumerate tested decorators and combinations;
candidate scope is not a compatibility claim.

## 7. Errors and cancellation

Build errors should identify the original function, generated node and conflicting
type/policy or unsupported feature. Invalid declarations fail before execution;
invalid run inputs fail before acquisition.

Execution and cleanup errors must preserve their original exception objects.
The probe demonstrated combined ordinary execution/cleanup faults. A production
contract must also preserve cleanup diagnostics alongside external cancellation
and exceptions raised by callers inside `open()`. Decide the carrier mechanism
before finalizing the public exception/result API; do not replace cancellation
with success, reduce errors to strings, or silently discard cleanup errors.

Repeated cancellation and cancellation during shutdown require dedicated checks
against the supported SDAX behavior. Declaring a retry on shutdown is explicit
permission for another attempt, distinct from replaying a callback merely because
external cancellation interrupted it. Exactly-once external effects are not promised.

## 8. Packaging boundary

Distribution name: `sdax-hamilton`. Proposed import name: `sdax_hamilton`.
Dependencies point from this package to `sdax` and `apache-hamilton`. NumPy/pandas
remain Hamilton's transitive dependencies and must not enter SDAX core.

Initially support a narrow tested dependency pair. The investigation's source
version labels do not establish that same-version published wheels behave
identically. Verify released artifacts before declaring installation bounds.
Keep Hamilton internals behind a small compatibility module and diagnose
unsupported versions explicitly.

This design targets Python SDAX. It neither requires a Rust binding nor claims
Rust-only service/effect capabilities.
