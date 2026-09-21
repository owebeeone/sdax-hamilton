# Decorator support plan — independent architecture and code-minimization review A6b

Date: 18 September 2026. Scope: architecture, product-code minimization, dependency
and maintenance cost, and the shortest safe route to broad decorator support.

Reviewed plan SHA256:
`ca1efd866cabaeb05309ae9bf3ca1408cb00c08d57368c2befcef99d8ab236dc`.

This review is independent of the other requested review. It changes no plan,
product source, workspace configuration or other review. Investigation was
read-only source inspection; no tests, probes, dependency installation, clones,
commits or external communication were performed. The sole created artifact is
this review. Workspace `AGENTS.md`, `AGENTS_GWZ.md` and `EVIDENCE.md` were read.

## Verdict

**Viable direction; amend the architecture and gates before implementation.**
Hamilton expansion plus SDAX execution is the right division. Keep ownership,
strict binding checks and failure cleanup: those are the frontend's useful
semantics, not unnecessary duplication. The plan correctly separates static
support from effective cache/Ray behavior, retains early release gates, rejects
unsafe aliases, and requires GWZ local clones rather than worktrees.

However, “minimal API intact” is not a sufficient code-minimization objective.
The proposed universal foundation, per-family adapters, recursive snapshots and
future registration contract could grow into a second Hamilton compiler while
leaving that API unchanged. The smallest credible design is an incremental
extension of the existing lowering boundary, with explicit evidence for every
additional representation, interception point and runtime mechanism. Broad
coverage should usually add qualification cases and small semantic corrections,
not a product subsystem per decorator family.

High findings below are pre-implementation design amendments, not claims of
observed new implementation bugs. Medium findings prevent avoidable scope or
maintenance costs. No measured implementation-duration or LOC claim is made.

## Evidence and reference conventions

`Plan` means `Decorator-Support-Plan.md`; `Inventory` means
`Decorator-Support-Inventory.md`. Line anchors refer to the reviewed files.
`Frontend` paths are relative to this repository. `Core` paths are relative to
`../sdax`. `H` is the inspected pinned Hamilton 1.90.0 installation at
`/Users/owebeeone/limbo/evidence-build-cache/sdax-hamilton-package/release-0.1.0/pypi-smoke/lib/python3.12/site-packages/hamilton`.
The machine-readable DAG is `decorator-support-dag.json`; its relevant edges
agree with the plan's diagram. “Verified” below means inspected implementation,
not execution reproduced in this review. Existing test bodies are evidence of
intended coverage, not a new test-run result.

Verified baseline:

- `Frontend/src/sdax_hamilton/hamilton_compat.py:224–306` already calls Hamilton
  expansion, converts results to immutable `NodeSpec` values, performs upstream
  edge checks and discards the mutable Hamilton graph.
- `Frontend/src/sdax_hamilton/_model.py:12–31`, `_selection.py:25–114` and
  `plan.py:16–43` already provide a graph model, selected execution shape and
  reusable prepared processor. A new representation must justify what these lack.
- `Frontend/src/sdax_hamilton/_runtime.py:82–105` lowers calls/checks to SDAX
  tasks; SDAX owns scheduling, retries and cleanup order. Separating calls from
  type checks deliberately prevents validation failures from retrying effects.
- Ownership is genuinely insufficient for new transformations:
  `hamilton_compat.py:286–295` applies `ownership_required=fn in owned` to every
  generated node, while `plan.py:163–164` checks direct releases when deciding
  whether outputs can escape `open()`. Owner/projection semantics need work.
- `Frontend/src/sdax_hamilton/_types.py:1–104` is deliberately a bounded
  checker, not a Python type prover. `Core/pyproject.toml:19` has no runtime
  dependencies; the frontend currently directly depends only on pinned SDAX and
  Hamilton (`Frontend/pyproject.toml:13`).

## Actionable findings

### M1 — High: make one persistent frontend graph and one execution path explicit

**Anchors:** Plan:6–8, 124–128, 137–147, 167–173; frontend `_model.py:12–31`,
`_selection.py:25–114`, `plan.py:16–43`, `_runtime.py:82–105`.

**Verified:** immutable lowering and execution-shape models already exist. P2
“introduces” a graph/provenance boundary and P4 owns plan/runtime/selection, but
the plan does not say whether this replaces, extends or parallels `NodeSpec`.

**Predicted cost/failure:** retaining a resolved graph, a semantic graph, an
ownership graph and the existing node mapping produces multiple editable sources
of truth. A validation alias can be correctly linked in one representation but
pruned in selection from another. Adding a role-specific scheduler or cleanup
walker would duplicate the hardest already-tested behavior.

**Minimal amendment:** P0 must state that P2 evolves or replaces the existing
private `NodeSpec` boundary; it does not add a second persistent executable graph.
Use temporary compiler records where needed, discard them after lowering, and
keep only facts consumed by selection, execution or supported diagnostics. P4
expresses ownership retention and effect ordering through the existing SDAX task
graph. Keep necessary call/check separation. Do not prescribe one file or ban
small cohesive dataclasses; constrain duplicate authority instead.

**Acceptance evidence:** a data-flow diagram identifies one authoritative
frontend dependency mapping and all new fields' consumers. A source audit finds
no frontend scheduling/retry/cleanup-order implementation and no Hamilton graph
retained merely to support ordinary execution. An acquisition → projection →
validation example demonstrates exactly one release and correct cleanup when
checking fails. Every additional task/edge has a named safety or semantic reason.

**DAG/gate impact:** add these constraints to P0 and P2/P4 acceptance, and check
them at QA/QB/QC. This is a constraint on existing work, not another framework lane.

### M2 — High: prove provenance capture without replaying Hamilton's compiler

**Anchors:** Plan:126, 132–141, 151–173; Inventory:71–86;
H `function_modifiers/base.py:738–762, 796–848`,
`recursive.py:306–311`, `validation.py:45–148`.

**Verified:** Hamilton itself orders resolution, creation, injection, expansion,
transformation and decoration. Recursive subdags call `base.resolve_nodes`
internally. Dynamic resolvers execute in `get_node_decorators`. Validation wraps
the producer, creates validators and returns an identity result gate. Final
ancestry is not a complete record of those transformations.

**Predicted cost/failure:** the phrase “semantic facts established by family
adapters” hides the critical implementation question: where are facts captured
before transformations erase distinctions? A separate pre-expansion interpreter
followed by ordinary Hamilton expansion may invoke dynamic resolution twice,
construct stateful validators/models twice, or implement different lifecycle
ordering. Inferring everything afterward from names is unsafe, as the plan knows.

**Minimal amendment:** before freezing a general family interface, require one
small composition fixture that demonstrates the actual capture mechanism. It
must delegate each Hamilton operation once per required declaration/mount
resolution, rather than replaying its pipeline. The candidate may use narrowly
bounded wrappers on copied modifier instances or another proven local seam;
this review does not assert such a wrapper is already sufficient. If interception
requires copied upstream logic, enumerate that exact logic, maintenance cost and
alternative before approval of the architecture. No global monkey patch.

**Acceptance evidence:** use a resource-bearing parameterized subdag with a
projection/validation alias, plus a counted delayed resolver returning a known
modifier. Record invocation counts, mount identities, original contracts and
owner retention. Compare Hamilton names/edges/values; verify existing Drivers
and the installed package are unchanged. Show which captured facts cannot be
obtained from final nodes. Do not require every family to pass before this slice.

**DAG/gate impact:** P0 freezes goals and a provisional interface; a joint P1/P2
vertical-slice checkpoint confirms the interface before wide family integration.
Keep unrelated tests/admission work parallel. This replaces speculative up-front
interface design, not the requirement for recursive admission.

### M3 — Medium: recursive snapshots need an explicit stopping boundary

**Anchors:** Plan:126, 162–164, 229–231; Inventory:98–102;
frontend `hamilton_compat.py:81–103`, `driver.py:12–15`, `docs/API.md:52–56`.

**Verified:** the current contract copies declaration/binding metadata but keeps
application object identities. Function clones retain globals and closure cells.
The inventory correctly excludes arbitrary application-state copying; the plan's
broader “helper references” and “deterministic snapshots” do not repeat that limit.

**Predicted cost/failure:** a generic recursive object snapshotter becomes an
unbounded graph copier. Copying a validator containing a lock, a model with a
client, or a bound literal with identity semantics can fail construction or alter
application behavior. Conversely, promising complete code immutability while
closures/globals remain live is inaccurate.

**Minimal amendment:** define a finite, family-aware list of declaration and
binding metadata containers to copy. Snapshot callable references/code only to
the published degree; preserve application values, globals, closures and stateful
instances unless a specific profile states otherwise. State per-driver versus
per-invocation ownership. Do not add generic deepcopy, serialization, state
discovery or locking merely to obtain “snapshot” status.

**Acceptance evidence:** metadata mutation cannot change a constructed Driver;
an identity-sensitive captured application object retains identity and follows
the documented state contract. Shared nested declarations terminate traversal
without duplicate copying. A stateful model/validator case either proves reuse
under its contract or is explicitly restricted. Record the exact mutation
guarantees rather than claiming arbitrary Python state is frozen.

**DAG/gate impact:** bound P2 in P0; let D1/D2/D3/E/F add only newly needed copy
rules with their fixtures. Do not make a universal snapshot service a QA prerequisite.

### M4 — High: P3 must extend bounded checking, not create a second type system

**Anchors:** Plan:31–41, 127, 182; frontend `_types.py:1–104`,
`hamilton_compat.py:106–140`, `_selection.py:87–101`, `plan.py:68–73`.

**Verified:** original merged bindings really can lose distinct requirements;
the frontend currently rejects those cases. It already has one shared bounded
annotation/value checker, and external-input requirements can already be a tuple
of contracts. TypedDict and unsupported pseudo-types are deliberately rejected.

**Predicted cost/failure:** “all generated and captured contracts” plus plugin
annotations can be read as a demand for general Python assignability, schema
inference and coercion. That introduces a broad maintenance project and may
delay simple aliases. Silently accepting Hamilton's merged annotation or replacing
unknown types with `Any` is the opposite unsafe shortcut.

**Minimal amendment:** enumerate the smallest admitted annotation grammar needed
by each feature. Extend the existing checker and preserve original requirement
sets; do not build a parallel type IR or solve arbitrary intersections. Distinguish
compile-time edge checks, literal/default checks and actual runtime representation.
Plugin schema validation remains delegated to its library. TypedDict support is
a specific feature with explicit required/optional-field semantics, not a promise
to interpret the whole typing module. Unsafe/unimplemented cases stay visible.

**Acceptance evidence:** each newly admitted form has a positive value/edge case
and an unsafe near-neighbor rejection. Test a source bound to two distinct
consumer requirements, grouped literals, tuple outputs and dict/model mismatch.
All checking paths use the shared primitives; no mandatory schema/type framework
dependency and no implicit `Any` substitution appear. Publish an admitted-form
table rather than an unbounded “all types” claim.

**DAG/gate impact:** P3 provides the common existing-type interface first; B/F/V
own their specific type extensions and join the relevant feature gate. QA should
not wait for plugin schemas or TypedDict work it does not consume.

### M5 — Medium: a work lane does not need its own adapter or public registry

**Anchors:** Plan:151, 167–173, 185; Inventory:16–19;
H `function_modifiers/expanders.py:425–477, 481–585`,
`adapters.py:119–148`; frontend `hamilton_compat.py:36, 162–170`.

**Verified:** convenience parameterization classes already delegate to upstream
`parameterize`; current admission rejects them by exact type. Hamilton's I/O
selection already implements registration precedence and an `Any` fallback.
The plan mandates each lane's “family adapter” and integrator registration;
X then proposes a registered extension mechanism.

**Predicted cost/failure:** an adapter class/file per public decorator duplicates
normalization and snapshot rules for aliases. A second I/O registry can select a
different loader than Hamilton. Building public plugin discovery now forces
stable extension APIs before built-in semantic needs are known.

**Minimal amendment:** say each lane owns qualification and only the product
changes it proves necessary. Allow test-only/admission-only lanes and shared
implementations across aliases. A small private exact-class mapping or dispatch
table is reasonable; do not replace fail-closed admission with unrestricted
`isinstance` acceptance of arbitrary third-party subclasses. Reuse Hamilton's I/O
registry. X remains optional and must not shape P2/P3 into a public SDK in advance.

**Acceptance evidence:** an implementation inventory maps decorators to shared
normalization paths and identifies why each special case exists. Alias families
share behavior rather than wrapper implementations. The same two competing I/O
registrations select the same adapter in Hamilton and the frontend. No public
entry-point loader, versioned adapter API or generic modifier protocol is required
for QA/QB/QC. F tests protocol integration rather than certifying an open world.

**DAG/gate impact:** retain X outside shipped coverage and out of P0 deliverables.
Files follow cohesive responsibilities, not the number of worker clones. The
integrator may merge tests with no new registration abstraction.

### M6 — Medium: use capability prerequisites instead of whole-family barriers

**Anchors:** Plan:63–88, 126–128, 158–165, 203–208, 242–255;
DAG `A.depends_on`, `QA.depends_on`, `C.depends_on`, `F.depends_on`,
`G1/G2/G3.depends_on`; H plugin `with_columns` implementations and
`recursive.py:306–311`.

**Verified:** A waits for complete P2/P3; QA waits for complete P4. Those shared
deliverables include nested snapshots, plugin annotations and full generated-role
ownership. C waits for U1 although its text ties U1 to async output pipes. F waits
for U2 although the reported defect concerns a generated loader tuple. Dataframe
plugins genuinely use recursive node collection, so deleting their recursive
foundation dependency outright would be incorrect.

**Predicted cost/failure:** harmless alias/tag admission waits for hard recursive
ownership and plugin typing. Sync pipeline or saver qualification cannot finish
while an unrelated correction is being investigated. “Start tests early” does not
remove those integration barriers in the machine-readable graph.

**Minimal amendment:** identify a small common contract slice sufficient for A
and direct owned parameterization. Gate A's qualified forms against that slice;
keep unsupported ownership compositions rejected. Let sync/replacement pipeline
and unaffected I/O subsets qualify independently, then join U1/U2 for their
affected promised forms. Keep full QB's requirement for all claimed built-ins.
For plugins, depend on proven recursive discovery/provenance capability, not
every public `parameterized_subdag` option unless actually consumed.

**Acceptance evidence:** each prerequisite edge names a concrete consumed
contract/test. A qualification can pass while a deliberately unresolved optional
schema or recursive-only case stays disabled. Coverage ledger and release notes
report partial profiles accurately; no resource case activates without its
ownership tests. The JSON and diagram must match after any split.

**DAG/gate impact:** refine the existing deliverables into a few capability
checkpoints; avoid proliferating a task for every decorator option. QA remains a
safety gate but no longer silently means “finish the universal compiler first.”

### M7 — High: K/R need an architectural feasibility gate before implementation

**Anchors:** Plan:21–29, 183–199, 210–213; Inventory:62–67;
H `caching/adapter.py:194–196, 1101–1147`,
`plugins/h_ray.py:142–179`; frontend `docs/API.md:26–28, 52–56`.

**Verified:** upstream caching is integrated with graph/node lifecycle hooks;
`pre_graph_execute` takes and retains a `FunctionGraph` and computes run-scoped
versions/behaviors. Ray's adapter accepts a Hamilton lifecycle callable and node,
returns object references and materializes results through a result builder.
These are broader contracts than preserving metadata. The plan acknowledges the
distinction but does not bound the product architecture required to bridge it.

**Predicted cost/failure:** achieving all upstream cache modes/invalidation and
Ray lifecycle semantics without upstream scheduling could introduce a shadow
Hamilton Driver, a hook bus, remote scheduler and cache-aware graph rewriting.
That is a second runtime project. The source inspection establishes coupling;
it does not establish that small integrations are impossible.

**Minimal amendment:** begin K/R with bounded feasibility deliverables: which
upstream components can be reused directly, which lifecycle calls are essential,
what state they retain, and which admitted effect/ownership cases are safe.
Prefer optional per-call integration over scheduler replication. If full parity
requires a second scheduler, core changes or broad lifecycle emulation, record
the gap and produce a separate design decision rather than automatically growing
the static decorator project. Preserve visible inactive status by default.

**Acceptance evidence:** demonstrate cache hit/miss/invalidation and remote
failure/cancellation on a small admitted profile while preserving the existing
prepared-shape and cleanup contracts. Inventory every bridge hook, retained
Hamilton object and new public configuration. Base imports/execution must not
need those backends. Unsupported owned/borrowing/effectful placements fail before
acquisition. A reduced profile cannot satisfy an unrestricted K/R claim.

**DAG/gate impact:** K/R begin with feasibility checkpoints and remain independent
of QA/QB/QC. Z may record unresolved runtime gaps and publish accurate audit
documentation, but its unrestricted-completion status remains blocked by those
gaps. Do not redefine incomplete parity as completion to meet a schedule.

### M8 — Medium: turn minimal core and bounded version coupling into release checks

**Anchors:** Plan:6–8, 124, 167–173, 179–199, 232–233;
frontend `hamilton_compat.py:1–5, 13–19, 48–69`, `pyproject.toml:13, 28–35`;
Core `src/sdax/__init__.py:1–5, 31–48`, `pyproject.toml:19`.

**Verified:** the current compatibility boundary deliberately confines Hamilton
internals; SDAX has no runtime dependencies. The plan forbids speculative core
API changes and keeps optional dependencies optional, but neither is a concrete
per-phase architecture test. Moving each adapter into a separate module could
accidentally spread imports/version assumptions through runtime code.

**Predicted cost/failure:** importing a central adapter registry imports Spark or
Pydantic during a base installation. A backend need results in “just one” SDAX
hook, or a Hamilton node leaks into `_runtime.py`, coupling two independent
release surfaces. Widening pins for a shim can silently admit unqualified versions.

**Minimal amendment:** make zero Hamilton-specific changes/dependencies in SDAX
core the default acceptance requirement. Any demonstrated exception gets its own
reviewed design and evidence, not a routine family edit. Permit one private
compatibility package to span cohesive files while keeping Hamilton internals out
of selection/runtime. Optional profile imports occur on demand. Each U1/U2 shim
records its version guard, exact semantic divergence, upstream regression and
retirement condition; an upgrade replaces the shim where possible.

**Acceptance evidence:** base-only installed-wheel tests run with optional
libraries absent; inspect direct dependencies and public exports against baseline.
A fast AST import audit checks the compatibility boundary, including branches not
executed by that test environment. Version mismatch tests fail closed. Upgrade
qualification enumerates changed internal touchpoints and removed shims. Report
any core/API delta explicitly instead of calling unchanged public names sufficient.

**DAG/gate impact:** put these constraints in P0 and enforce them at each release
gate and optional-profile integration. No new mandatory runtime dependency is
introduced solely for snapshots, registries or a generic type/graph framework.

### M9 — Medium: centralize qualification without constructing a test or ledger framework

**Anchors:** Plan:31–36, 124–125, 151–173, 215–233;
frontend `tests/test_compiler.py:27–59, 84–145, 275–327`,
`pyproject.toml:34–35`.

**Verified:** there is already a Hamilton-vs-frontend oracle, module factory,
compile-once test and snapshot regression. Some baseline tests intentionally
reject features that the new plan intends to admit. The sdist includes `tests`
and `docs`, but does not include `dev-docs`.

**Predicted cost/failure:** each lane invents its own comparison harness and
copies the cancellation matrix; fixes then diverge. Conversely, interpreting
“retain the original 175 regressions” literally preserves obsolete unsupported
assertions or forces redundant tests merely to retain a number. A runtime support
registry generated from the ledger adds another source of admission truth; public
tests depending on a ledger fixture left only in `dev-docs` fail from sdist.

**Minimal amendment:** evolve the existing public test utilities. Use shared,
table-driven role-level lifecycle cases plus focused family-specific structure
and composition tests. Preserve baseline behaviors, replacing obsolete rejection
cases with acceptance plus remaining-negative controls when support expands.
Keep the ledger as qualification/reporting data; it must not become a runtime
graph interpreter or independently maintained admission registry. Any CI-needed
data belongs in the shipped public test inputs.

**Acceptance evidence:** one common oracle helper, a requirement-to-test mapping,
and explicit records of replaced baseline rejection assertions. Run the common
lifecycle suite against each new semantic lowering path, not mechanically every
alias spelling. Include selected cross-family cases where compositions change
behavior. Wheel-from-sdist CI works without `dev-docs` or private evidence unless
the packaging manifest deliberately includes required public data.

**DAG/gate impact:** P1 supplies shared helpers; lanes supply cases. QA/QB/QC reuse
the accumulated suite and add tests for newly admitted semantics, rather than
duplicating all baseline scenarios in every lane. Gate counts are evidence, not
the definition of correctness.

## Explicit P0 goals and non-goals suitable for the revised plan

The following is proposed plan language, not a description of completed work:

> Minimize product machinery while expanding qualified coverage. Reuse Hamilton
> for decorator lifecycle ordering, expansion, generated callables and upstream
> validation; reuse SDAX for task scheduling, policy execution and cleanup order.
> Extend the existing private immutable frontend representation only with facts
> needed for binding checks, acquisition identity, known borrowing/alias lifetime,
> effect targeting and supported diagnostics. New product abstractions require a
> concrete admitted case and a demonstrated limitation of existing structures.

> A family may complete through admission and tests alone. Prefer shared semantic
> normalization over an adapter per spelling. Keep one bounded checker, one
> authoritative frontend graph, one selected execution shape and one SDAX
> execution path. Preserve necessary call/check and validation-gate dependencies;
> do not add barriers unrelated to actual data, effects or lifetime requirements.

> No Hamilton-specific changes to the minimal SDAX core, no second Hamilton
> compiler/executor, no generic Python type prover, no generic Python object
> snapshotter, no persistent plan format, and no new public plugin framework are
> required for shipped static-decorator coverage. Cache/Ray are separately gated
> optional profiles; broad lifecycle emulation requires a separate design decision.
> Optional libraries remain optional, compatibility shims remain version-bounded,
> and unknown unsafe combinations remain explicit limitations.

These goals allow necessary frontend changes. In particular, owner identity and
known borrowing aliases cannot be replaced with ancestry guesses simply to save
code. The useful constraint is fewer independent mechanisms, not an arbitrary
line-count quota.

## Per-phase minimization gates

| Phase | Required architecture evidence |
|---|---|
| P0 | Responsibility map; existing structure to extend for each requirement; explicit non-goals; provisional annotation grammar and snapshot boundary; no runtime/public schema designed solely for X/K/R. |
| P1/P2 | One compositional provenance slice with counted resolution; one authoritative lowered representation; temporary compiler state discarded; original modules/package unchanged. |
| P3 | A bounded admitted-type table; original consumer requirements preserved; shared checking primitives; no hidden schema coercion or `Any` fallback. |
| P4 | One acquisition owner per instance; aliases retain lifetime; selection/replacement/escape checks agree; SDAX still owns execution and cleanup; all extra edges justified. |
| A–F | Per lane: shared path reused, precise missing fact/correction added, upstream expansion retained, tests added, dependencies/API/internal touchpoints listed. A test-only change is a valid outcome. |
| U1/U2 | Narrow guard and reproducer; preserve exception/cancellation/type semantics; no installed-package mutation; copied source attributed; removal/upgrade condition recorded. |
| G1–G3/V | Optional imports and dependency profile; reuse recursive/validation foundations; no new scheduler/type framework; exact representation and cancellation limitations visible. |
| K/R | Reuse/bridge feasibility before implementation; no implicit new scheduler or core change; bounded admitted profile plus explicit remaining parity gaps. |
| X | Separate optional proposal after built-in needs stabilize; no shipped-coverage dependency; reuse proven private mechanisms only if a public extension API is justified. |
| QA/QB/QC | Dependency/import/public-API audit; accumulated public regressions; no duplicated family runtime machinery; qualified claims match ledger; packaging works without optional/private material. |
| Z | Fresh inventory and version-touchpoint audit; report unresolved cases honestly; unrestricted coverage requires all corresponding semantic gates, not decorator-name enumeration. |

The worker-isolation procedure should remain GWZ local clones, provisioned and
integrated serially as already specified. Worker boundaries may separate tests
and evidence while sharing a small product implementation. Do not create one
permanent subsystem per clone, use worktrees, or sweep unrelated workspace dirt
into this campaign.

## Smallest architecture to attempt first

1. Discover and snapshot the bounded supported declaration metadata, including
   nested declarations and shutdown associations. Keep application state identity.
2. Delegate expansion to pinned Hamilton once per actual resolution context;
   collect only the semantic facts that final generated nodes cannot establish.
3. Lower into the existing frontend node model with original contract requirements,
   acquisition identity and known borrow/effect relationships. Keep tags as data.
4. Use one selection/validation path and the existing SDAX lowering/runtime.
   Reject combinations whose required semantics cannot yet be established.
5. Grow support by qualified shared paths and profiles. Introduce new mechanisms
   only when the compositional tests show a specific need.

This preserves the plan's useful broad-support objective while making minimal
product code an explicit, reviewable deliverable rather than an aspiration.

---

## Secondary independent review — revised plan

Date: 18 September 2026. The first review above is preserved unchanged. This
second pass independently reviewed the revised plan, inventory and JSON DAG;
the other review report was not consulted. Investigation remained read-only
apart from appending this section. No implementation or conformance tests were
run. A read-only structural check parsed the three planning artifacts and checked
the DAG, without creating a runner or experimental artifact.

Reviewed SHA256 values:

| Artifact | SHA256 |
|---|---|
| `Decorator-Support-Plan.md` | `dba5f0c287155f40d9b8a240ca45348581d3abc7fc3162846947eb4efc85a25e` |
| `Decorator-Support-Inventory.md` | `437161aaff7ac794b7d1797ec0fd8a506723be6ed89a187dc2149741948bb6ba` |
| `decorator-support-dag.json` | `54c0b58da609e1eea54f0cde0d590f8a8b53aac4aecbf67c39e066f8ea18458f` |

### Verdict: proceed with the planned first implementation stages

**All M1–M9 are addressed at the plan level. No architecture/code-minimization
plan blocker remains.** Proceed with P0/P1 and the independently safe A path;
proceed with broader foundations only after S demonstrates the capture seam.
K0/R0 retain real go/no-go authority. This is approval of the implementation
direction and its gates, not evidence that broad decorator support, provenance
capture or backend bridges already work.

The revision makes the intended small architecture explicit: extend the existing
NodeSpec/checker/selection/runtime, delegate Hamilton expansion once per actual
context, preserve one SDAX execution path, and justify any additional fact or
mechanism by a concrete consumer. It permits qualification-only family work,
keeps optional extensions out of the public API design, and makes minimal core,
dependency boundaries and compatibility-shim retirement measurable gate items.
The added safety policies generally fit this boundary: role-aware selection,
captured adapter identity and a narrowly bounded validation final-gate correction
are frontend responsibilities, not authorization to build a generic policy engine.

### First-pass dispositions

Line references below refer to the revised plan identified by the hash above.
“Addressed” means the planned remedy is sufficiently explicit; its listed tests
remain future implementation obligations.

| Finding | Disposition and evidence |
|---|---|
| M1 — One graph/execution path | **Addressed.** Plan:23–31 and 218–220 explicitly evolve NodeSpec, discard temporary state, preserve one persistent dependency authority and leave scheduling/retry/cleanup order with SDAX. Plan:397–405 audits mechanisms and boundaries. No parallel graph or executor is prescribed. |
| M2 — Capture without compiler replay | **Addressed.** S is now an explicit feasibility task before P2/P3, with the required counted resource/subdag/projection/validation/resolver slice (Plan:217, 224–230). The wrapper is a candidate rather than an assumed solution; copied compiler logic requires an architecture review. |
| M3 — Bounded snapshots | **Addressed.** Plan:32–36 and 232–237 identify finite metadata copying, callable-reference limits, application-state identity and memoized shared/cyclic traversal. No generic deep copier or locking mechanism is required. Inventory:124–128 preserves the state/reentrancy distinction. |
| M4 — Bounded types | **Addressed.** Plan:213, 219, 250 and 259–263 reuse the checker and original requirements, attach added annotation forms to consuming features, and reject generic inference/intersection machinery. Nominal representation versus plugin schema validation remains explicit at V (Plan:314). |
| M5 — No adapter/registry per lane | **Addressed.** Plan:241–246 permits admission-only/test-only work and shared private dispatch; Plan:267–272 retains upstream selection precedence and captured adapter identity. X is a later optional proposal (Plan:386–388), rather than a foundation SDK. |
| M6 — Capability prerequisites | **Addressed.** QA has only A/P1/P0 as ancestors. C/F no longer depend on U1/U2, while QB explicitly joins the corrections. D0 is the consumed plugin capability; G1/G2/G3 do not depend on D1, D2 or D3. Plan:70–75, 215–216, 250–260 and 436–441 match these choices. The minor shared-gate wording below does not negate the explicit early-path policy. |
| M7 — Backend feasibility | **Addressed.** K0/R0 must demonstrate a bounded bridge before K/R and cannot silently adopt a FunctionGraph runtime, hook bus, scheduler or core change (Plan:101–105, 323–328). QK/QR join composition qualification. Static Z and runtime ZR are separate, and reduced profiles cannot claim full parity (Plan:76–83, 378–384, 427–432). |
| M8 — Core/dependencies/version coupling | **Addressed.** Plan:55–58 prohibits Hamilton-specific core changes within this plan; Plan:316–319 and 401–405 require absent optional dependencies in the base profile, AST boundary checks and exact shim version/retirement rules. Splitting compatibility files does not relax the boundary. |
| M9 — Common qualification/ledger | **Addressed.** Plan:92–95 makes the ledger reporting-only and ships CI data publicly. Plan:214 and 406–425 reuse the existing oracle/role suite, replace obsolete rejection cases explicitly and require wheel-from-sdist tests. Test counts and one framework per family are no longer objectives. |

### DAG and prose consistency checks

The structural check verified **33 unique task IDs and 63 edges**, with exact
Mermaid/JSON node-title and edge equality, known prerequisite IDs, no cycles,
and exact agreement between every `depends_on` set and its `consumes` keys.
The task descriptions were also read, not merely parsed.

- The early path is `P0 → P1 → A → QA`. Neither S/P2/P3/P4 nor plugin/backend
  work is an ancestor of QA. Plan:215–216 preserves baseline owned shapes while
  keeping new transformed/recursive ownership unsupported until qualified.
- S precedes P2/P3; P4 and family work then consume their concrete outputs.
  S is a feasibility slice, not completion of B/D1/D2/E in advance. Its outcome
  must establish the seam without turning that slice into another retained compiler.
- G1 consumes B and D0; G2/G3 consume D0. D1 finishes public subdag options but
  is not a hidden prerequisite for plugin development. Their release qualification
  still joins ownership and wider composition work through QB at QC.
- C/F can finish their unaffected subsets while U1/U2 proceed independently;
  QB includes both corrections directly. This matches Plan:251, 257 and 440–441
  and Inventory:73–74. It does not advertise corrected async/loader coverage early.
- Z depends on QC and has no K/K0/R/R0/X ancestor. QK depends on K and QB; QR
  depends on R and QB; ZR joins Z/QK/QR. Their aggregate core-composition gates
  are now explicit safety/qualification choices, not concealed backend dependencies
  in the static release path.
- X depends on QB, but is not a predecessor of any shipped-coverage gate. GWZ
  local-clone isolation remains explicit in both artifacts; there is no worktree
  substitution or requirement for a permanent product module per worker.

No missing edge, cycle or contradictory backend-activation prerequisite was found.

### New or regression findings

**N1 — Low, nonblocking clarification: scope the shared composition list to the
capabilities being activated.** Plan:392 introduces requirements at every
QA/QB/QC/QK/QR gate, and item 5 (Plan:411–416) lists extraction, subdag and
validation compositions without repeating “applicable.” Read literally in
isolation, it could make QA wait for unsupported families despite the explicit
contrary rules at Plan:70–73, 215–216 and 436–441.

This is a wording ambiguity, not a remaining plan blocker: the specific QA
contract and authoritative DAG both clearly preserve the early path. The minimal
amendment is to start item 5 with “For the capabilities being activated, run the
applicable compositions.” Acceptance evidence is a QA job whose declared cases
exercise A/current owned shapes and do not require new subdag/plugin support;
QB/QC then add the wider compositions. **DAG impact: none.** No safety case for an
activated capability may be dropped through that clarification.

No new high or medium architecture finding was identified. In particular, the
larger planning document does not itself imply a larger product implementation:
its additional constraints mostly forbid unneeded mechanisms and require small
qualified seams. The narrow diagnostics deviation is a real compatibility cost
to track, but Plan:291–305 already bounds it and records the upstream difference.

### Remaining implementation acceptance obligations, not plan blockers

1. **S must work in real pinned Hamilton.** A local interception mechanism has
   not yet been demonstrated. Resolution counts, composed owner/projection facts
   and unchanged upstream/package state remain the decisive evidence. If S fails,
   broad expansion stops for redesign while A/QA may continue.
2. **P2/P3/P4 must remain one implementation.** Review actual fields, retained
   state and tasks/edges against consumers. Memoized declaration traversal must
   not become arbitrary object copying; feature-specific contracts must not grow
   into a second type system. Import-boundary checks alone do not prove these facts.
3. **D0 supplies provenance, while P4/QB/QC establish usable lifetime behavior.**
   Distinct mount IDs alone are insufficient evidence of independent cleanup.
   Family completion remains separate from activation, as Plan:259–260 requires.
4. **The validation correction must stay narrow.** Reuse validator computation
   and levels, preserve user exceptions, and qualify role/selection/logging behavior
   without installing a process-global filter or a generic secret-redaction engine.
5. **K0/R0 must be permitted to fail.** A smaller admitted cache/remote profile
   must retain visible gaps; do not force feasibility by importing an executor or
   core hooks. QK/QR's optional combinations need their own actual evidence.
6. **Release assertions need executable checks.** Base-only installed packages,
   bounded version mismatches, public shipped fixtures and the accumulated
   composition/lifecycle suite remain work to implement. Planning dispositions
   and ledger rows do not substitute for these results.

Proceed under those gates. The revised architecture is small enough in intent,
and specific enough in its rejection/stop conditions, to begin implementation
without another planning redesign.

### Final-hash addendum — N1 closed

Date: 18 September 2026. Verified the final plan SHA256:
`cd4358d97305c82483f7e87e29417ea0e28b72e25be11971dd673e91c2504627`.

The sole change since the secondary-reviewed plan makes shared gate item 5 read:
“**Compositions:** for the capabilities being activated, run the applicable
compositions”. Reversing that exact wording replacement recovers secondary-review
SHA256 `dba5f0c287155f40d9b8a240ca45348581d3abc7fc3162846947eb4efc85a25e`.
Inventory and DAG hashes remain unchanged from the secondary review.

**N1 is closed. The proceed verdict stands, with no outstanding architecture
plan findings.** The implementation acceptance obligations above remain; this
narrow verification does not claim implementation qualification.
