# Compiler foundation architecture review A6b

Date: 18 September 2026. Reviewer lane: independent architecture and code
minimality. Scope: the bounded P2 provenance foundation, P3 binding-contract
foundation and construction-failure transport. This is an integration gate for
later P4/E and family work, not a qualification of the decorator families used by
the private proof entry.

## Frozen inputs

- P2 commit: `24f7787a2b855a6c2e211a54dc7c021de44c57b6`
- P2 compiler hash:
  `2daf0261de87971075930042a6ea3dc124ce0115e060805cb7d1be9caa8862ef`
- P2 model hash:
  `e64fc13f955618b6dc5a92742420ea490a176505ba6fc51657c55380c89132bf`
- P2 regression hash:
  `fe3b1191f32ab04c98ecf88ef593f7492c302d9a720db05c099c8c1051ff76ac`
- P2 report hash:
  `8ded11c04e8081ab21001e7375c73f17e94893f1f6c49028848ee32f02a50402`
- P3 commit: `76a5d5603051e7eaf369126b9d43e1b60ffb4cba`
- Construction-failure helper commit:
  `654f39c19c1fecb7fb0f22e627eb28c21dc7dad9`

The P2 focused suite passed 6 tests and the merged source suite passed 252 tests
under the external qualification interpreter with bytecode and pytest caches
disabled. The P3 worker snapshot passed its 202-test suite. The construction
helper's five focused tests passed. The reviewed P2 diff had no whitespace error.

## Verdict

**Proceed with the compiler foundations.** P2 now establishes one production
compilation/lowering path that can capture generated-node provenance without
replaying Hamilton, inferring roles from names, retaining a Hamilton graph or
patching process-global state. P3 adds the minimum immutable input-contract field
and reuses the existing selection, preparation and runtime checks. The private
construction transport prevents Hamilton's unconditional exception logger from
formatting user callback failures while retaining the original exception object
and single callback execution.

This verdict is deliberately bounded. The private `_supported` entry admits proof
families only to the gate tests. It does not activate recursive composition,
extraction, delayed resolution or validation in the public allowlist. P4 and E
must consume the captured facts and pass their own selection, ownership and
diagnostic gates before those families can be advertised.

## Architecture assessment

The compiler remains the sole graph authority. It discovers and structurally
validates declarations, calls the pinned Hamilton lifecycle once for each actual
declaration context, lowers the returned nodes into the existing immutable
`NodeSpec` mapping, asks Hamilton to check dependency compatibility, then discards
all Hamilton construction objects. `PreparedPlan` and SDAX remain the only
execution and cleanup authorities. There is no retained `FunctionGraph`, second
runtime graph, copied `resolve_nodes` algorithm or lifecycle replay.

P2 observes four pinned lifecycle seams on copied instances:

1. `extract_fields.transform_node()` identifies its returned source and
   projections by the upstream return contract.
2. validation transformation identifies evidence, final gate and raw value by
   the pinned return ordering.
3. `resolve_from_config.resolve()` is called once and its copied returned
   validation modifier is observed during the same lifecycle pass.
4. `parameterized_subdag` hands facts from each child mount to its parent before
   `add_namespace()` replaces the node objects.

Correlation uses a construction-local mount token plus callable identity. A
strong callable reference prevents `id()` reuse while a fact is pending. Nested
namespace handoff moves the fact into the parent mount before the next namespace
copy. The final role is therefore derived from the actual modifier output and
mount operation rather than generated names. Tests cover two independent roots,
nested mounts and distinct per-mount resolver configuration, so the exact-once
witness distinguishes the actual mount contexts.

Ownership is derived after every declaration has resolved. This matters for a
top-level projection whose acquisition owner belongs to another declaration root.
The compiler traverses the existing Hamilton dependency mapping, stops at actual
owned calls and records the resulting owner names in `borrow_from`. It attaches a
shutdown only to an actual acquisition call. Projection, validation raw and
validation gate nodes retain borrowing facts without becoming acquisition owners.
Validation evidence is separately role-labelled and carries no owner claim.

The two new `NodeSpec` fields have named downstream purposes. `role` distinguishes
ordinary values, projections, raw validation values, validation evidence and
final validation gates for E/P4 selection and diagnostics. `borrow_from` records
the acquisition nodes P4 must preserve against projection, override and config
bypass. Neither field currently activates behavior by itself.

P3 does not introduce a parallel type representation. `InputSpec.requirements`
is an immutable tuple beside the existing effective edge type. Empty requirements
fall back to the existing `typ`, preserving old callers. Selection checks every
requirement for generated edges, defaults, config values and external inputs;
preparation checks overrides before a runner exists; the runtime callback checks
generated inputs immediately before the consumer even when output checking is
disabled. The existing `_types` functions remain the only compatibility oracle.

## Construction diagnostics

Hamilton 1.90 wraps `resolve_nodes()` in `except Exception` and logs the complete
exception automatically. A config predicate, model constructor, delayed resolver
or validator can therefore place sensitive callback text in an automatic log even
when the frontend's validation policy is data-minimal.

The correction is narrow. Each already copied modifier lifecycle is wrapped so an
ordinary `Exception` becomes a private `BaseException` transport. Hamilton's
ordinary-exception handler does not catch or log that transport. One outer helper
calls the real `base.resolve_nodes()` once, catches the transport, leaves the
`except` block, and re-raises the original exception object with its original
traceback. Nested transports pass through unchanged; `KeyboardInterrupt`,
`SystemExit`, `CancelledError` and other `BaseException` values are not converted.
Dynamic resolver results are copied, provenance-instrumented and then wrapped
before Hamilton invokes their lifecycle.

The integrated public-Driver regression proves the failing predicate runs once,
the caller receives the same exception with no transport context/cause, Hamilton
emits no raw exception record, and an application log deliberately emitted by the
callback remains visible. No logger, handler, filter or import hook is changed.
The construction-failure regression also proves the provenance capture becomes
unreachable after failure. This closes a concrete retention path: before the
transport, Hamilton's logged `exc_info` retained the compiler frame and capture
even after the capture tables were cleared.

## Findings and disposition

The initial P2 snapshot had a dead helper-clone table and duplicate function-copy
implementation. `_copy_function()` also temporarily delegated to an unfinalized
capture object, coupling the pipeline correction helper to provenance. The final
snapshot restores one bounded module-level copy routine, removes the dead table
and lets provenance instrument the modifier snapshots already made by that
routine. Modifiers are not copied twice.

The initial exact-once assertion recorded two identical resolver values, which
proved total calls but did not directly distinguish the two mounts. The final
fixture supplies distinct low/high configuration and asserts each value once.
Additional nested-mount and independent-root cases prove mount handoff and prevent
same-name facts from crossing roots.

The initial namespace implementation keyed final facts by node name and did not
carry an already namespaced inner fact into an outer mount. The final implementation
hands the callable/fact pair to the parent mount at the namespace boundary. The
nested test now retains projection role and the correct namespaced owner.

The initial delayed-resolver wrapper instrumented the returned modifier directly.
The final version copies that modifier first, so the construction pass does not
leave instrumentation on an application-owned object.

The first disposal evidence covered successful construction and a later runtime
validation failure. It did not exercise compiler unwinding. A construction-time
failure regression was added, and its first run exposed Hamilton's logger retaining
the capture frame. Integrating the private failure transport removed that retention
and made the failure-path weak-reference assertion pass.

P3 had no blocking architecture finding. It preserves conjunctions without a
second map, exercises zero-effect external and override paths, rejects an `Any`
runtime mismatch and preserves the existing release-once behavior. Its snapshot
wording was also corrected from a stronger immutable/frozen claim to an isolated
metadata-list snapshot where appropriate.

## Remaining gates

E must remap an explicit shutdown declaration target to the captured actual raw
call after validation renames the call. The current default
`@shutdown(of=resource)` proof is valid because the raw call is the sole actual
candidate. It does not qualify `target_="resource"` when Hamilton has generated
`resource_raw`. Validation cannot be publicly activated until that case is defined
and tested.

D0/D2 and each later family still require exact-class admission, recursive shape
validation, supported-option tests, mutation snapshots and composition evidence.
The private proof allowlist is not evidence for public family support. P4 must use
`role` and `borrow_from` to prevent selection, config and override paths from
bypassing acquisition ownership or mandatory validation. E must use the role facts
for its data-minimal diagnostic behavior. Cache and Ray tags remain inert metadata
until their separate runtime gates.

Hamilton's own modifier-package import probes installed default-validator
packages, including Pandera, even with registry autoload disabled. Preventing that
would require a different upstream dependency or process-global import
interception. The accepted plan amendment therefore distinguishes upstream trusted
import probes from frontend backend activation: sdax-hamilton does not activate an
optional backend from tags or data, its own optional-profile imports remain
explicit, and base-only CI omits optional packages. The isolated import regression
characterizes the Pandera probe and confirms inactive Ray metadata does not request
the Ray runtime. No product import filter is warranted.

`hamilton_compat.py` is now about 800 lines. The present growth is cohesive around
one pinned compiler boundary, and splitting it during this gate would move code
without reducing authority or complexity. As additional family hooks arrive,
separate the narrow provenance-capture and binding-analysis helpers from the
orchestration module when they have stable consumers. Do not replace the exact
family hooks with a generic public decorator framework or one wrapper class per
decorator; that would increase the extension surface without reducing the pinned
Hamilton coupling.
