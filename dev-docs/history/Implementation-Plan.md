# Implementation plan

Date: 18 September 2026. Status: original implementation proposal, retained as
the roadmap. See [Implementation-Status.md](Implementation-Status.md) for the
current alpha implementation, executed validation and remaining work.

For expansion beyond the released 0.1.0 subset, use the newer
[decorator support plan](Decorator-Support-Plan.md), its inventory and dependency
DAG. That plan supersedes this document's broad deferred-decorator ordering.

## Scope and working rules

- Implement an optional frontend package; leave the Python SDAX core API minimal.
- Use GWZ for workspace member structure, status, staging and commits. Do not
  hand-edit `gwz.conf` or treat this member as an unrelated checkout.
- Keep portable product code, tests, contracts and CI fixtures in this repository.
- Keep campaign-only runners and raw experimental evidence in the appropriate
  private evidence member. No public build or test depends on that member.
- Do not promote a prototype by copying its entire evidence harness into product
  code. Extract the supported behavior into maintained, standalone tests.
- No remote publication, upstream issue/PR submission, or release is part of
  creating these documents.

## 1. Resolve contracts and dependency baseline

Finalize the proposed `Driver`, prepared-plan operations, `execution`, `shutdown`
and `Acquisition[T]` forms in [API-Design.md](API-Design.md). Explicitly decide:

1. Discovery of shutdown declarations and scope-local policy registries, including
   repeat imports, multiple drivers and transformed functions.
2. The initial acquisition restriction and a path for explicit partial-state
   publication. Keep acquisition retries disabled until attempt cleanup exists.
3. Runtime input checking, `None`, `Any`, intentional awaitables and override rules.
4. How cancellation/caller exceptions and cleanup faults are exposed together.
5. Supported Hamilton source/release versions and handling of async output pipes.

Review the small candidate Hamilton fix with public, minimal regression cases.
The probe found an internal unannotated async identity in `pipe_output`, also
used by `mutate`. Prefer an upstream correction; a full fork is not the default.
Any upstream communication requires separate authorization. An unsupported form
can be rejected while unaffected functionality proceeds.

**Acceptance:** a written contract for the first supported subset and exact
dependency inputs; candidate features remain visibly deferred. Do not require
the entire future resource model to begin the pure-dataflow translator.

## 2. Package and declaration compiler

Create a standalone Python package and public tests using existing SDAX APIs.
Use a small module boundary for each responsibility, initially along these lines:

| Module | Responsibility |
|---|---|
| `declarations.py` | New policy/shutdown declarations and typed state definitions. |
| `hamilton_compat.py` | All access to Hamilton graph/node internals and version checks. |
| `compiler.py` | Validation and translation into immutable binding specifications and SDAX tasks. |
| `driver.py` | Graph construction and explicit plan preparation. |
| `plan.py` | Per-run context creation, execution, scoped results and failure handling. |

These are proposed source boundaries, not a requirement to create empty files.
Keep graph construction separate from invocation state. Do not invoke Hamilton's
scheduler under the translated plan or implement another retry scheduler.

Port the proven static cases: plain sync/async functions, binding, defaults,
parameterization, output extraction, configuration selection and data subgraphs.
Retain compatible ordinary Hamilton imports. Add signature preservation checks
for the new declarations and appropriate static typing checks for author examples.

**Acceptance:** supported graphs yield the same ordinary values as Hamilton;
declared edge mismatches, missing inputs and cycles fail before effects. Generated
names and edges are inspected, not just final outputs. Tests run from a standalone
checkout against public dependencies, without the private archive.

## 3. Prepare once and run repeatedly

Implement explicit `prepare()` with fixed outputs, optional-input presence and
override-node structure. Store one reusable SDAX processor per prepared plan.
Every call creates new context, acquisition records and phase-runner state.

**Acceptance:**

- Instrument compilation to prove repeated sequential and concurrent runs of one
  prepared plan perform one compilation, while accepting different input values.
- Prove no cross-run result, exception or ownership-state leakage.
- Reject shape mismatches before acquisition; never silently rebuild in a
  prepared plan's execution method.
- Show immutable policy/binding snapshots cannot be changed through the driver
  while a plan is running. Document application-owned mutable input/config objects.
- Separate in-memory plan reuse from result caching and resource lifetime.

Convenience automatic plan caching is a later milestone. First make explicit
reuse observable and correct; no performance claim follows merely from reuse.

## 4. Execution policy and shutdown

Translate `execution` settings into existing SDAX `TaskFunction` settings. Bind
shutdown to the selected acquisition node's `post_execute`. Use a per-run state
record with explicit availability; publish a returned resource before validating
it or making it available downstream.

**Acceptance:**

- Verify per-attempt timeouts, retry counts, eligible/ineligible exceptions,
  exhaustion, external cancellation and the delegate backoff contract.
- A timed-out attempt stops before a retry starts. If child scopes are exposed,
  verify children stop before retry as well, using SDAX's owned scope.
- Parent and child resources release in dependency-reverse order after success,
  ordinary failure and cancellation of concurrent consumers.
- Shutdown runs for started acquisition even without a published result; a
  published `None` remains distinguishable from absence.
- A failed output check still releases the returned resource.
- A failing or timed-out child release does not silently suppress parent release.
- Preserve execution/cleanup exception objects, including the agreed behavior for
  caller exceptions inside `open()` and cancellation during shutdown.
- Duplicate/ambiguous shutdown targets and forbidden resource overrides or
  acquisition retries fail before executing application callbacks.

Include negative controls that remove dependencies or release registration;
the assertions must catch the resulting failures. The existing probe supports
several of these behaviors, but is not evidence that all acceptance cases pass.

## 5. Compatibility and scope validation

Create an enumerated conformance matrix for each supported decorator and its
relevant combinations. Test both sync and async forms where promised, rather
than assuming a decorator's presence establishes async compatibility.

Add explicit targeting cases for parameterized resources, extracted values and
resource-bearing subgraphs. Keep unsupported ownership combinations rejected.
Verify that rejecting a known unsupported adapter/version/dynamic node gives a
useful error before acquisition. Preserve Hamilton's ordinary declaration
semantics while documenting intentional stricter runtime validation.

**Acceptance:** a public support table corresponds to runnable tests and names
the tested dependency versions. A correction to one Hamilton internal stays
isolated in the compatibility boundary; do not accumulate scattered patches or
global monkey patches to imply unsupported compatibility.

## 6. Documentation and initial release readiness

Provide complete examples for ordinary dataflow, plan reuse, scoped resources,
timeout/retry, and combined execution/cleanup failure. Explain how a familiar
Hamilton driver-shaped interface connects at the graph level, and which executor
features do not transfer automatically.

Validate installation from the intended distribution artifacts in a clean
environment. Verify that installing/importing SDAX alone still requires no
Hamilton dependency. Run the public tests without the private evidence member.
Choose and document a license before distributing implementation code; preserve
required provenance/notices if upstream source is copied rather than imported.

**Acceptance:** documented and tested subset; stable initial ownership/error
contracts; reproducible installation; no unsupported claims about hard timeouts,
static ownership, durable recovery or Rust-only features. Publication itself is
a separate user-authorized action.

## Deferred work

- Automatic bounded prepared-plan caching, including invalidation and concurrent
  cache misses.
- Partial-acquisition publication beyond the initial constrained form and safe
  resource-acquisition retries.
- User child-task scope authoring and richer shutdown dependencies.
- Dynamic expansion/collection via nested plans, if justified by use cases.
- Materialization, cache adapters, remote execution and specialized dataframe
  integrations, each with its own semantics and conformance cases.
- Any first-class result typing beyond checked graph edges and a dynamic result
  mapping; any cross-run resource scope or persistent checkpoint format.

## Decision triggers

If Hamilton graph internals prove too unstable, first seek a supported graph
export boundary or narrow the supported version range. If dependency cost is
unacceptable for target users, evaluate a native declaration compiler separately.
If a lifecycle behavior cannot be expressed through current SDAX callbacks and
context, produce a minimal counterexample before proposing a core change.
None of these possibilities is authorization to widen SDAX preemptively.
