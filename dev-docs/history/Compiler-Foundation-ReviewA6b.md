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

## Final foundation addendum

The later hooks 1–4 snapshot and mechanical cohesion split pass this bounded
architecture gate. The reviewed snapshot is based on commit
`08273176ff31a08370914c77f369b5a906dba8ca` and has these final hashes:

- `hamilton_compat.py`:
  `e66f8e91f8a6f677dbd1ab15684cf64f7fdc04c3b0da22e97d2c83309866bc5e`
- `_hamilton_provenance.py`:
  `c0ecd46350d0c2ad1260258818b11ba0f0980689e954405ff89c78b45d847620`
- `_hamilton_pipeline.py`:
  `283b2cf9232169ff6705f0797585caca35ba2d38149eb46f86c64d8d644968cc`
- `test_provenance_feasibility.py`:
  `617a4a58bef4a0b829bac3ae16b2a8b08d21249de28a1c4ce050c1e596d7ef4d`
- `test_macro_capture.py`:
  `65047e596e161f9eb95bce78cf85290559250460cf32137a6c3391638b041508`
- `Provenance-Feasibility.md`:
  `52eee7c21ee7ff03c11cd8bbd86de1f47ee690adf137d632e8cc38bfa341ea76`

The independent full suite passed 288 tests with caches disabled, and the diff
check was clean. The new private provenance module owns only copied-modifier
interception, callable/mount fact handoff, borrow discovery and construction-time
disposal. Version and admission checks, declaration and shutdown validation,
recursive discovery, public-target mapping, Hamilton edge checking, lowering and
`compile_modules()` remain in `hamilton_compat.py`. This is the cohesive split
anticipated above; it adds no second provenance representation, copied compiler,
runtime graph, replay, global patch or decorator framework.

The additional exact hooks remain compiler preparation. Public `_SUPPORTED`
admission is unchanged. D0 still needs public recursive-mount qualification, C
needs its full macro and composition gate, F must classify loader and saver roles,
and E must complete validation targeting and diagnostics. A selected pipeline
helper must currently be discovered from a supplied module or recognized recursive
declaration source. An external undiscovered helper is rejected after the one
trusted delayed-resolver callback and before runtime effects. Pipeline helpers and
`does` replacements must be exact Python functions; callable instances are
rejected before expansion because their mutable state and SDAX policy provenance
have not been qualified. A plain-function `does` replacement remains the
implementation of the decorated owner, while a plain-function pipeline step is a
separate discovered graph call and retains its own policy and shutdown facts.

The bounded B binding helper also passes. Its foundation and two corrections are
commits `ea94c1f6f806b1d52b039863a0edc044bf5f5d60`,
`fb8042ce9be5f69861125718953d9e2eb4c62d4b` and
`004f27db9f5b72dbd56cf2a5939fdcd67671e1ec`. Final hashes are:

- `_hamilton_bindings.py`:
  `f24b566cda1c8071f0bf66e231f6828b84c23e6e5359590a14d92f94d7bf9856`
- `test_binding_contracts.py`:
  `f6d304cb9694e48a1ddc0bf0fd05db991d3a0b8e45dbb9b2bd97b8ade5f6cb32`

All 28 focused tests passed. The helper records every original consumer contract
in the existing `InputSpec`, makes any required merged consumer decisive, retains
only identical-object defaults, and gives a literal already bound to the rewritten
source its upstream precedence. Optional list and dictionary groups follow
Hamilton's own optional unwrapping before its exact container-origin checks.
Snapshotting preserves literal payload identity. There is no alternate binding
executor, contract map or intermediate representation. Integration must replace
the older compatibility-layer binding validation and one-level snapshot path
rather than retain both implementations. This approves the shared B foundation;
it does not activate the B decorator families by itself.

The optional-profile identity guard passes at commit
`c1ec1cb4a638e8b1cf1d9a74dedcf11f3df57f09`. Its final hashes are:

- `_optional_profiles.py`:
  `2340eb21d3c3ead27f485a56712b375742f6ec14f0a34362bd9f854a90c6d59f`
- `test_optional_profiles.py`:
  `02085942a61a25dc5f877d558cd40701d090bc53aa4e756ab21a094768987f0f`

All four direct guard tests passed. The guard compares the modifier's exact class
with a fixed attribute read from an already loaded shipped plugin module using
`vars(module)`. It neither imports a backend, invokes module `__getattr__`, scans a
registry nor admits subclasses. Identification and pinned distribution validation
remain separate, and merely loading or probing a plugin module has no effect until
its exact modifier is attached to a declaration and that family is admitted. The
explicit decorator import is therefore sufficient profile selection; no Driver
argument or public plugin SDK is needed. The guard is inactive infrastructure and
does not qualify or activate any optional family.

### Shared input-contract transport seam

The construction-only input-contract seam passes its bounded architecture gate at
these frozen hashes:

- `_hamilton_provenance.py`:
  `fc2785390c7ecc5465ce9bc54e05616dbe584499c3d572dd811eb323757ce33f`
- `hamilton_compat.py`:
  `4a3f6b6f367f378bcdc42d5f8462420c6994a829c90f776e31600e2d5a241e81`
- `test_provenance_feasibility.py`:
  `d155014f348bcdb1e08fb70442a1a0e659339e11d287e35f85013e508d8d88e5`

The independent run passed 13 focused and 319 full tests with caches disabled;
the diff check was clean. `_CapturedFact.input_contracts` transports the existing
immutable `InputSpec` objects during construction. It is not another contract
model or persistent registry. `_remember()` rejects contract keys that are not
inputs of the observed Hamilton node. Namespace handoff checks the input count and
the exact ordered `(type, DependencyType)` values before applying the pinned
Hamilton 1.90 key-order rename; a two-input witness proves correct remapping and
fail-closed rejection of distinct-type reordering. `_lower_inputs()` then writes
the captured requirements and defaults into the sole final `NodeSpec.inputs` map.

Extraction, validation and output-pipeline transitions preserve the relevant
incoming declaration, role, actual-call, borrow, public-name and contract facts
instead of attributing a transformed call to the outer modifier by accident. The
separate E composition witnesses prove role, declaration and shutdown routing;
they do not seed nonempty contracts or cross a namespace. This approval therefore
covers the shared transport seam only. B/C producer capture and a real D0
namespaced nonempty-contract composition remain required before their public
families can be activated.
