# Hamilton versus independent frontend: executed comparison

Date: 18 September 2026, Australia/Sydney. Runs dated 17 September in UTC.
Status: bounded prototypes, not a production API or release qualification.

## Decision supported by this comparison

**Both approaches are viable for the tested subset. The A6 review does not justify
abandoning Hamilton or changing SDAX core.** An independent frontend also works,
but it must solve the same lifecycle, binding and error problems. Several defects
discovered during this comparison were in that shared work, not Hamilton.

Keep the typed binding/ownership representation and SDAX lowering independent of
Hamilton. Treat Hamilton as one declaration compiler feeding that representation.
This gives a practical exit path without maintaining two schedulers or burdening
the minimal Python SDAX API.

Given the original objective of genuine Hamilton decorator compatibility, the
recommendation is to continue with the bounded Hamilton integration over this
independent frontend layer. Keep the native prototype as a comparison/reference
until there is a reason to ship a second authoring API. If dependency footprint
or control of the authoring language becomes the primary goal, the native route
is now an executed alternative, not a speculative rewrite.

No maintained Hamilton fork is warranted by these results. No SDAX or Hamilton
product source was changed for this comparison.

## What was built

Two agents independently implemented declaration compilers while the primary
agent implemented the common backend and acceptance harness:

```text
Actual Hamilton declarations ── Hamilton compiler ─┐
                                                 ├─ typed node/ownership specs
Independent native declarations ─ native compiler ┘
    → one prepared SDAX processor
    → fresh invocation context and acquisition records
    → existing SDAX dependency execution, retry/timeout and reverse shutdown
```

Live prototypes are in the ignored
[`scratch/frontend-comparison`](../scratch/frontend-comparison/README.md) directory.
They include separate runnable examples, separate compilers, a common runtime,
and a shared test suite. Copies of every executed version are preserved in the
private campaign archive; scratch is not the only copy of the evidence.

The shared backend deliberately isolates the variable being compared: declaration
compilation and its effect on ownership/binding information. A shared test passing
for both frontends does not independently prove the runtime twice.

## Results and retained failures

| Run | Outcome | Meaning |
|---|---|---|
| `2026-09-17-comparison-01` | 49 passed, 12 failed | Five harness name-collision failures; one native ownership failure; six failures exposing three common-backend defects across both frontends. Both example programs passed. |
| `2026-09-17-comparison-02` | 67 passed | Fixed the recorded defects and expanded cancellation/release coverage. |
| `2026-09-17-comparison-03` | 72 passed | Removed an unnecessarily broad Hamilton resource restriction; added shared expanded-ownership and Hamilton config/resource cases. |
| `2026-09-17-control-01` | All 4 selected checks failed | Removing dependency edges breaks both frontends' lifecycle assertions. |
| `2026-09-17-control-02` | All 4 selected checks failed | Removing shutdown callbacks breaks both frontends' release assertions. |

Both example programs ran successfully in every baseline run, each reusing its
prepared plan twice. A separate process also imported the native frontend without
loading Hamilton. This is an import-boundary check, not a clean-install test or a
dependency/import-time benchmark.

The 72 checks include parameterized instances and deliberate rejection tests;
they are not 72 distinct supported decorators. They cover:

- Parent/child acquisition, concurrent consumers and dependency-reverse release.
- A consumer failure cancelling/draining its sibling before resource release,
  with original execution and cleanup exception objects retained.
- Caller cancellation during execution, a second cancellation during cleanup,
  and cancellation arriving while cleanup follows a caller-body exception.
- Scoped resource access; direct resource output rejected by `execute()`.
- Per-attempt timeout/retry with the previous attempt's `finally` completed before
  the next attempt starts; release timeout followed by parent release.
- Output checks that do not replay forward side effects; cleanup return checks
  that do not repeat a completed release through retry policy.
- Invalid returned resources retained as raw objects without falsely granting
  validated typed access; published `None` distinguished from absence.
- Input/default/literal/edge checks, a heterogeneous tuple case, invalid policy
  values, selected config/override ownership protection and dependency cycles.
- Optional-input shapes, pruning overridden work, direct parameterization and
  explicitly targeted releases for each selected resource expansion.
- One instrumented processor construction across 12 overlapping runs and another
  sequential run per frontend, with separate values and resource records.
- Actual Hamilton output equivalence on a small parameterized/injected/configured
  graph, and configuration alternatives with their own shutdown declarations
  without renaming application functions across drivers.

## What the comparison changed

### Runtime obligations belong in a common frontend layer

The first run reproduced three common-backend mistakes: an optional consumer's
type constraint was omitted when another consumer made the input required;
checking a release's return type inside its retryable callback repeated cleanup;
and a shutdown-originated `CancelledError` could disappear through SDAX's internal
child-task handling. These affected both compilers. The revised frontend records
all selected input contracts, excludes framework validation failures from retry
decisions, and retains release interruption objects for reporting after cleanup.

Forward execution is lowered into a retryable call node followed by a separate
non-retried validation node. Ownership and shutdown remain attached to the call
node. A rejected output therefore keeps its cleanup obligation. This uses ordinary
existing SDAX tasks/dependencies; it is not a new core execution phase.

The experimental acquisition record distinguishes raw availability, typed validity
and typed access. It does not make an arbitrary invalid object releasable: the
release author still needs a defensible raw-value failure path.

Cleanup uses the public phase runner and a retained, awaited drain task protected
from further caller cancellation. The prototype propagates caller cancellation
after draining and attaches concurrent diagnostics in `exception.sdax_failures`.
A caller-body exception remains the same object unless later caller cancellation
takes priority, in which case that body exception is retained in the diagnostics.
Callback-originated cleanup cancellation is retained in the aggregate failures;
it is distinct from externally cancelling the caller. These are tested candidate
semantics, not a finalized public exception API.

### Native ownership was not automatically correct

Initially, native parameterization allowed one expansion to have a shutdown while
another selected expansion of the same acquisition had none. This was a real
prototype hole, not a Hamilton issue. Both compilers now retain an ownership
requirement on every sibling of a declared acquisition. Preparation rejects any
selected sibling without a release, while allowing an owned selected subset.

This records known declaration provenance. It cannot detect arbitrary user
functions returning the same singleton through two supposedly separate acquisitions.

### Hamilton's first restriction was too conservative

The first Hamilton compiler rejected all multi-node resource expansion. Inspection
showed that the admitted ordinary `parameterize` wrappers each call the original
function directly; they are not extraction/validation aliases. Supporting explicit
ownership on those outputs required extending the existing per-origin target map,
not another Hamilton patch or another scheduler. The final shared tests exercise
both fully owned expansions and rejection of a selected unowned sibling.

This correction matters: the earlier prototype restriction must not be reported
as a fundamental inability of Hamilton to represent parameterized acquisitions.
Resource extraction/validation transformations remain separately restricted.

## Actual differences remaining

| Area | Hamilton prototype | Independent prototype |
|---|---|---|
| Authoring compatibility | Imports real admitted Hamilton objects and their graph resolution behavior. | Implements a small native surface; similar spellings do not promise Hamilton compatibility. |
| Plain/injected/parameterized sync and async calls | Executed and checked. | Executed and checked. |
| Direct parameterized acquisitions | Explicit per-output ownership supported in final run. | Same tested obligation. |
| Configuration alternatives | Uses actual Hamilton config resolution; owned alternatives tested. | No equivalent config decorator implemented; callers choose modules/declarations explicitly. |
| Optional parameter rebound to another source name | Explicitly rejected in this prototype. | Omitted/default and supplied-input forms executed. |
| Owned extraction and `check_output` transformations | Rejected before execution; explicit ordinary validation nodes work. | No matching transformation API implemented; explicit ordinary validation nodes work. |
| Dependency footprint | Requires Hamilton and its dependencies. | Native import does not load Hamilton. |
| Compatibility maintenance | Reads Hamilton decorator metadata and invokes `resolve_nodes`/`update_dependencies`; clones functions to isolate config name mutation. | Owns its small binding/compiler implementation and future feature maintenance. |

Neither prototype supports arbitrary modifiers, grouped bindings, materializers,
caching adapters, dynamic expansion, remote executors or complete Python typing.
The Hamilton arm is deliberately narrower than the older broad feasibility probe:
this comparison focused on lifecycle guarantees and defensible early rejection.
The missing cases are future work, not disproved capabilities.

## A6 disposition and remaining release gates

| Review concern | Evidence from this comparison |
|---|---|
| A6-01: generated ownership | Direct parameterization works with origin tracking; unsafe resource transformations are rejected. General transform composition remains open. |
| A6-02: invalid `Acquisition[T]` | Separate raw and validated access tested. Arbitrary invalid-object cleanup is still an author contract. |
| A6-03: exit/cancellation | Named caller/body/cleanup and repeated-cancellation cases pass; no claim about all possible interleavings. |
| A6-04: complete binding checks | Tested literals/defaults/edges/inputs and selected type forms. Full type matrix and mutable declaration objects remain release work. |
| A6-05: replacement ownership | Selected ordinary and expanded resource replacements rejected for config and runtime overrides. |
| A6-06: retry boundary | Forward and release validation failures do not replay successful effects in the tested cases. User effects themselves remain author-controlled and may repeat. |
| A6-07: discovery | Multiple drivers and configured ownership tested without application-function renaming. General module/subgraph/plugin discovery remains limited. |
| A6-08: policy validation | Named malformed counts/durations/exception specifications rejected by the shared declaration layer. |

Still unresolved or unqualified: publication during partial acquisition, cleanup
between acquisition attempts, cross-run resources, alias escape, application child
task ownership, deep immutability/reentrancy of captured literals and validators,
complete annotation support, sync offload, hard deadlines, installation from
published artifacts, and wider Hamilton version support. No throughput, memory,
import-cost or adoption measurement was performed. Prepared-plan reuse is
in-memory reuse; it is not persisted execution state.

The next product step should extract the tested internal binding/ownership model
and runtime contracts into maintained public tests, then implement the chosen
supported Hamilton subset against those contracts. Do not promote these scratch
prototypes wholesale or turn the private archive into a build dependency.

## Provenance

Executed on macOS 26.6.2/Apple Silicon, Python 3.12.12 and pytest 9.1.1. The SDAX
revision is `e178637c4f577eadaa33af0c7fe10524b6183918`; Hamilton is the existing
snapshot `d55da91947da4a8036e35c8ed452e95b01028a09`. Each run fingerprints the actual
working package bytes rather than relying only on version labels. Runtime copies
were checked unchanged after execution, and current source bytes were compared
with the final manifest before reporting.

[Campaign and frozen runs](../../sdax-core-evidence/campaigns/frontend-comparison/README.md)
— **private evidence member; access required**. Each run contains its frozen runner,
source hashes, exact commands, environment/package inventory, raw test log, XML
results and outcome. Failures and controls are retained separately. These local
research references are optional; they are not standalone public CI dependencies.
