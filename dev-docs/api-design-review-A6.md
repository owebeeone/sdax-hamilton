# Adversarial API design review A6

Date: 18 September 2026. Status: review of a proposal, not a shipped implementation.

## Verdict

**Proceed with the separate graph-translation frontend, but do not freeze the
resource or failure API yet.** The architectural split is justified by the
existing experiment. The draft is not yet a sufficiently precise contract for
implementing its lifecycle guarantees. Several difficult cases are correctly
acknowledged, but others can bypass the proposed safeguards even when the author
uses explicit targets and valid-looking declarations.

The strongest case for this package is checked Hamilton-style composition with
SDAX-managed execution and dependency-derived shutdown. A pure-dataflow subset
is a useful implementation milestone; by itself it does not demonstrate the
package's strongest advantage over Hamilton. Conversely, broad decorator
coverage is poor compensation for ambiguous resource ownership.

None of the findings establishes a need to widen SDAX's minimal Python API or
maintain a Hamilton fork. Resolve frontend contracts and produce focused
counterexamples first. Replacing SDAX with application-managed task groups and
exit stacks is not a recommendation of this review.

## Scope and evidence standard

Reviewed [API-Design.md](API-Design.md), [Implementation-Plan.md](Implementation-Plan.md),
the workspace feasibility report, the probe source and selected dependency
implementations. Review baselines, SHA-256:

```text
API-Design.md
1f00ecda49948af461e2dae3ba60882f37e1fa4b808b5920ed509782a8832d41
Implementation-Plan.md
9dac602211f089a5c29238617cbb2e3885f61e52d9faa6f383f581e94b32fc40
```

Line references below refer to these document bytes. Dependency observations
refer to the locally inspected source, including Hamilton snapshot
`d55da91947da4a8036e35c8ed452e95b01028a09`. They are not claims about every release.
No new runtime experiments were performed for this review. Counterexamples are
proposed acceptance cases, supported by source inspection where identified.
Prior probe results remain bounded evidence for their recorded tests.

P1 means resolve before shipping the affected guarantee. P2 means resolve before
freezing the relevant API or advertising the capability. An acknowledged open
issue is identified as such; it is not presented as a newly discovered product bug.

## Findings

### A6-01 — P1: An explicit node target does not establish acquisition ownership

**Location:** API design lines 128–144, 155–158, 262–268; implementation plan §5.
**Status:** new gap within the acknowledged transformed-resource problem.

The design rejects ambiguous targets but does not specify which unambiguous
targets are legal owners. A node may return a resource acquired by another node.
Attaching shutdown to that node can be too late to establish cleanup eligibility.

For example, Hamilton's `check_output` transformation constructs an acquisition
node named `database_raw`, validator nodes, and a final `database` node. The final
node returns the raw value only after validation succeeds. If shutdown explicitly
targets `database` and the final validation gate raises, `database_raw` has already
returned the handle but the owner's wrapper has no returned value to record. Its
shutdown sees `has_value=False`. If a validator itself raises earlier, `database`
may never start, making its shutdown ineligible altogether. The translation chose
the wrong owner in either case.

The same transformation makes retrying the final node different from reacquiring
or revalidating the resource. Two distinct pass-through nodes can also refer to
one handle; rejecting duplicate ownership of the *same node name* does not catch
that double ownership. Arbitrary application alias analysis is out of scope, but
known Hamilton-generated aliases are within the compatibility boundary.

**Required decision:** define supported acquisition origins and how ownership
survives each supported transformation. For initial support, reject ownership on
known validation/identity/projection nodes unless the compiler can establish a
unique acquisition origin and preserve its cleanup eligibility. Do not equate
“explicit target” with “valid owner.” Reject unsupported resource combinations
before any selected acquisition runs.

**Acceptance:** a resource with failing output validation is released exactly
once by its acquisition owner; targeting a generated final alias is either
translated safely or rejected. Include two generated aliases of one acquisition,
parameterized acquisitions, and resource-bearing subgraph mounts.

**Source basis:** Hamilton
[`BaseDataValidationDecorator.transform_node`](../../scratch/hamilton/hamilton/function_modifiers/validation.py)
constructs the raw/validation/final nodes; SDAX
[`_post_should_run`](../../sdax/src/sdax/sdax_core.py) checks `pre_started`.

### A6-02 — P1: Failed output checking contradicts the unconditional `Acquisition[T].value: T` promise

**Location:** API design lines 134–156; implementation plan §4.
**Status:** new internal contract conflict.

The design rightly requires retaining a returned object for cleanup before
validating it. However, after a type check rejects that object, shutdown still
receives `Acquisition[T]` whose `value` supposedly has type `T`. `has_value` proves
availability, not type correctness. A typed release function can therefore receive
the very value already proven incompatible with its annotation.

This is more specific than the general warning that Python function bodies can
lie. With `check_outputs=True`, the frontend knows the type claim is false and
deliberately delivers the object across a typed boundary anyway. The existing
probe's wrong-output test uses `states.append`, so it proves retention and delivery,
not a safe typed release contract.

**Required decision:** distinguish raw ownership state from validated typed
access. For example, expose a separately named raw value typed as `object`, with
typed access conditional on successful validation; define who can release an
invalid object. Alternatively, explicitly document this cleanup channel as an
unchecked emergency contract. Neither approach can promise to manufacture a
valid resource from an arbitrary invalid return value. Keep downstream delivery
blocked and retain both validation and release failures.

**Acceptance:** return an incompatible object from an acquisition and exercise a
real release function that accesses resource-specific operations. Verify the
documented state, object retention, blocked consumers and complete diagnostics;
an append-only release callback is insufficient.

**Source basis:** private probe
[`test_output_check_failure_still_releases_returned_resource`](../../sdax-core-evidence/campaigns/hamilton-frontend/runner/test_bridge.py)
returns a string from a function annotated `dict` and delivers it to `states.append`.

### A6-03 — P1: `open()` needs a closure and exception contract, not just an error carrier

**Location:** API design lines 140–144 and 317–327; implementation plan §1 and §4.
**Status:** acknowledged issue; source inspection makes its implementation consequence concrete.

The current SDAX phase runner's `__aexit__` calls `raise_failures()` only when no
exception is already leaving the caller's scope. Simply nesting its context
manager therefore does not meet the frontend requirement to expose cleanup
failures alongside a caller exception or external cancellation. Its public
`failures()` method supplies useful information, but the frontend must explicitly
use it on those paths.

Repeated cancellation is also a closure problem. `aclose()` awaits phase work;
if interrupted, `run_next()` moves back to the post phase, while already-started
post callbacks are filtered out. That prevents accidental callback replay. It
does not, by itself, specify how the frontend finishes remaining cleanup before
returning control, or what it reports about a release interrupted before completion.

**Required decision:** write the frontend exit state machine before freezing
`open()`. Define body success/failure/cancellation, cleanup success/failure/
interruption, repeated cancellation, and the point at which the scope is closed.
Specify how original exception objects remain accessible while cancellation
remains observable. Do not merely put `CancelledError` inside an ordinary error
wrapper and assume callers will still see cancellation semantics. Use the existing
public phase-runner operations first; no need for a second scheduler is established.

**Acceptance:** cover the cross-product above, including a second cancellation
during child release, a parent still awaiting release, and simultaneous body and
release errors. Assert task termination and resource state as well as exceptions.
Verify that explicitly configured release retries remain distinguishable from
replaying a callback after external interruption.

**Source basis:** SDAX [`AsyncPhaseRunner`](../../sdax/src/sdax/sdax_core.py),
especially `__aexit__` at line 538, `run_next` at 552, `aclose` at 586 and `failures`
at 618. The design already correctly records the probe's missing coverage.

### A6-04 — P1: Graph-edge checking does not validate every declarative binding

**Location:** API design lines 4–9, 257–280 and 296; implementation plan §1–2.
**Status:** new coverage gap, plus an acknowledged type-matrix decision.

Hamilton's parameterizer removes literal-bound parameters from generated node
inputs and captures their values in a callable. Thus an author can use
`@inject(limit=value("many"))` for a parameter annotated `int`, leaving no visible
producer/consumer edge for the frontend to check. The inspected parameterizer
validates parameter names and grouped shapes, but does not generally type-check
literal values. Python defaults present a related binding boundary.

Checking selected external inputs and declared edges cannot establish the broader
promise of checked parameter passing unless these captured bindings are included,
or explicitly excluded from that promise. The needed information may have to be
collected before Hamilton finishes graph construction.

Blindly reusing Hamilton's `check_instance` would also be insufficient for a broad
runtime type guarantee. Its inspected implementation checks every tuple element
against the first type argument. By inspection, `(1, "x")` fails against
`tuple[int, str]`, while `(1, 2)` passes. Fixing permissive `None` handling alone
does not establish a sound supported type matrix.

**Required decision:** enumerate the validation boundary: graph edges, external
inputs, overrides, config values, decorator literals/group members, defaults and
optional output checks. For each, specify supported annotations, validation time,
and rejection behavior for unsupported forms. Preserve literal-binding provenance
where validation is promised. Do not describe declared edge checks as static
verification of function bodies or Python ownership.

**Acceptance:** invalid injected and parameterized literals, grouped constants,
defaults, heterogeneous tuples, unions and the documented `Any` escape hatch.
Invalid supported declarations should fail before executing graph callbacks;
unsupported annotation forms should produce a deliberate diagnostic.

**Source basis:** Hamilton
[`parameterize.expand_node` and `validate`](../../scratch/hamilton/hamilton/function_modifiers/expanders.py),
particularly literal binding around lines 286–298; and
[`htypes.check_instance`](../../scratch/hamilton/hamilton/htypes.py) at line 417.
The tuple examples are source-derived, not new executed probe results.

### A6-05 — P1: Configuration replacement must obey the resource override prohibition

**Location:** API design lines 179–180, 199, 222–245 and 257–263.
**Status:** new unaddressed replacement path.

Hamilton configuration is not only graph-selection metadata. During graph
construction it skips generated computation nodes whose names occur in config
and supplies external/config nodes instead. `Driver({"database": borrowed},
application_nodes)` can therefore replace the acquisition before preparation
examines runtime `override_nodes`.

A compiler that finds ownership only on surviving computation nodes can lose the
resource declaration. One that attaches shutdown to the replacement can close a
borrowed resource. The existing prohibition on runtime resource overrides does
not state what happens on this earlier replacement path. Requiring every selected
owner target to remain an acquisition node could close the hole, but that rule
needs to be explicit.

**Required decision:** apply ownership checks to all replacement channels,
including configuration and generated subgraph bindings. Preserve declaration
provenance through config pruning. Reject replacing a selected owned acquisition
until borrowed ownership is supported. Also specify config/input collisions and
whether unknown or unused values are rejected; do not accidentally change graph
shape by merging dictionaries at invocation.

**Acceptance:** config replacing a selected owned node fails before callbacks;
ordinary documented config replacement works; an unselected config alternative
does not become a spurious required owner. Test relevant runtime input collisions
and replacement of a generated owned node as well.

**Source basis:** Hamilton [`create_function_graph`](../../scratch/hamilton/hamilton/graph.py)
skips `n.name in config` around lines 190–192 and creates external config nodes.

### A6-06 — P1: Define what a retry repeats, including compiler-added validation

**Location:** API design lines 89–100 and 264–268; implementation plan §4–5.
**Status:** new behavioral gap.

The probe places binding, callable execution, result resolution and output
validation inside one SDAX-retried callback. If an author permits `TypeError` or
`Exception`, a deterministic frontend output-check failure can replay a function
that already performed an external side effect. Retrying a generated validation
or identity node has different effects: its upstream function is not rerun.

Consequently, the same-looking function-level declaration can repeat different
work after decorator expansion. Per-node retry delegation is reasonable, but it
is not a function transaction, a subgraph retry, or a guarantee of replay-safe
inputs. Mutable arguments and resources survive across attempts unless explicitly
replaced; a failed attempt may already have changed them.

**Required decision:** state exactly which generated callback region is retryable
and how deterministic frontend failures are classified. If validation must never
trigger user-work replay, arrange the translation accordingly using existing
callbacks/dependencies, or otherwise prove its exclusion from accepted retry
policies. If the whole wrapper is intentionally retryable, make that behavior
explicit and test it. Document that retry permission covers potentially repeated
side effects and reused mutable inputs. Never silently expand it to upstream work.

**Acceptance:** a side-effect counter plus invalid output under a broad retry
policy; a consumer mutating an input before failure; a validation/final node with
retry policy; and a generated acquisition node for which retries are forbidden.
Assert invocation counts and retained state, not just the final exception.

**Source basis:** private probe [`Bridge._callback`](../../sdax-core-evidence/campaigns/hamilton-frontend/runner/bridge.py)
includes validation inside the callback passed to `task_func`; SDAX
[`_execute_with_retry`](../../sdax/src/sdax/sdax_core.py) repeats that callback.

### A6-07 — P2: Shutdown discovery has no selected implementation contract

**Location:** API design lines 63–71, 128–136 and 257–259; implementation plan §1.
**Status:** acknowledged open issue with API consequences.

Hamilton discovers public functions defined in supplied modules. A metadata-only
`shutdown` decorator on the ordinary `close_database` function shown in the draft
does not automatically exclude that function from discovery. Exclusion therefore
needs an explicit frontend mechanism compatible with the chosen Hamilton version.

Likewise, `of=database` is a Python function reference, while selected Hamilton
nodes may be renamed by config, expanded into several nodes or mounted more than
once. Merely collecting module attributes does not define which release declaration
wins across supplied modules or whether imported releases are included. Mutating
the source module during construction would create interference between drivers.

**Required decision:** choose and document scoped discovery and immutable
function-to-node provenance. For example, specify exactly which supplied modules
contribute declarations and how shutdown functions are excluded without mutating
application modules or global Hamilton behavior. Define conflicting execution
declarations, repeated imports, absent config alternatives and target namespaces.
Keep unresolved ownership combinations rejected.

**Acceptance:** build two differently configured drivers from the same modules,
in both orders and concurrently; verify identical discovery and unchanged module
contents. Cover a release in a second module, transformed acquisition names,
duplicate declarations and a config branch that is not selected.

**Source basis:** Hamilton [`graph_utils.find_functions`](../../scratch/hamilton/hamilton/graph_utils.py)
at line 29; private probe declarations use a manually supplied registry and do
not implement this proposed authoring form.

### A6-08 — P2: Delegating policy execution does not delegate complete declaration validation

**Location:** API design lines 89–100 and 313–315; implementation plan §4.
**Status:** new validation gap.

The design promises invalid declarations fail before execution but leaves numeric
domains and exception specifications unspecified. The inspected SDAX
`TaskFunction.__post_init__` checks ranges, not all runtime types or finiteness.
For example, `retries=1.5` passes its negative check but cannot be used by the
execution loop's `range`. A NaN timeout passes a simple less-than-zero check.
An invalid exception tuple can remain dormant until a callback fails.

If these reach a running graph, another acquisition can already have executed
before a declaration error is discovered. Frontend validation is precisely part
of the intended higher-level boundary; fixing this does not require widening core.

**Required decision:** specify integer retry counts, numeric duration/backoff
domains, treatment of booleans, zero, NaN and infinity, and valid exception class
tuples. Validate inherited/resolved policies at preparation. Explicitly reject
retry classes broad enough to include external cancellation, consistent with the
draft. Pin and document the delegated default exceptions and jitter behavior.

**Acceptance:** malformed policies fail preparation before a sentinel acquisition
can run. Test broad base exception classes, invalid tuple members, fractional
counts and non-finite values alongside the chosen legal boundaries.

**Source basis:** SDAX [`TaskFunction.__post_init__`](../../sdax/src/sdax/tasks.py)
at line 48 and [`_execute_with_retry`](../../sdax/src/sdax/sdax_core.py).

## Concerns that should remain explicit, without inventing more blockers

- **Partial acquisition is honestly deferred.** That is a material limit for a
  lifecycle product. Initial examples must demonstrate the supported small
  acquisition pattern, including responsibility for failure before return. An
  unpublished shutdown record is not leak recovery. This is already in the draft;
  it is not a newly discovered defect or a reason to burden core.
- **Plan reuse and concurrent user code are different promises.** Per-run contexts
  isolate frontend state. Hamilton-generated callables may retain `value(...)`
  objects and validator instances; Python defaults and application closures can
  also be mutable. Add these to the documented reentrancy boundary and conformance
  tests. Do not deep-copy arbitrary resource-bearing objects to manufacture isolation.
- **Compatibility needs execution-trace assertions.** Ordinary values can match
  Hamilton while effects, validation, retry counts or cleanup differ. The proposed
  matrix should include lifecycle interactions, not only one decorator per row.
- **Failure-before-effects must be scoped.** Graph construction can execute
  author-supplied configuration resolvers, and importing modules can have effects.
  Promise validation before selected execution/acquisition callbacks, not before
  every possible effect of loading application code.
- **Dependency and adoption costs remain unmeasured.** Actual Hamilton decorators
  are a strong compatibility advantage for existing Hamilton users. For new users,
  that benefit must justify the dependency footprint and supported-subset learning
  cost. The feasibility counts establish neither demand nor performance.

## Recommended changes to the implementation plan

1. Keep pure-dataflow translation as an early milestone, but resolve A6-04 and
   A6-08 for its advertised supported types and policies. Publish a small explicit
   compatibility matrix rather than a broad family-level claim.
2. Before shipping lifecycle support, resolve A6-01, A6-02, A6-03 and A6-05 as one
   coherent ownership/exit contract. Implement A6-07's scoped discovery before
   relying on the proposed decorators in user examples.
3. Define A6-06's retry boundary before promoting transformed-node policies.
   Use acceptance tests that inspect invocation counts, started owners, released
   owners and exception identity. Retain negative controls for dependency/release
   removal, and add cases that target the wrong generated owner.
4. Make the first end-to-end release gate a typed async acquisition, a dependent
   resource, concurrent consumers, failure/cancellation, and reverse release,
   executed repeatedly through one prepared plan. Require a standalone public
   test against the intended distribution artifacts. A larger decorator count
   should not substitute for this scenario.

Approve implementation of a bounded frontend with these gates. Do not approve
the initial resource API as stable merely because the earlier prototype passed
its recorded cases. Pursue a Hamilton correction or core change only when a
specific supported behavior cannot be implemented correctly at this boundary.

## Evidence references and access

The [feasibility report](../../HAMILTON-FRONTEND-FEASIBILITY-2026-09-17.md) provides
the prior results and limitations. The
[campaign archive](../../sdax-core-evidence/campaigns/hamilton-frontend/README.md)
and probe links above require access to the **private evidence member**.
Dependency source links require the surrounding workspace and Hamilton scratch
snapshot. These are research references, not dependencies of this repository's
public build or tests. The findings state the relevant source behavior so the
review remains readable in a standalone checkout.
