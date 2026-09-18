# Hamilton coverage execution record

Started: 18 September 2026. Scope: the static coverage path through Z in
[Decorator-Support-Plan.md](Decorator-Support-Plan.md). Cache/Ray remain separate
feasibility projects; the proposed SDAX core changes remain deferred.

## Baseline and gates

Clean workspace checkpoint: `0cce004fb6f2ad26a395f4a505e422a9a0e02c2d`.
Frontend checkpoint: `80ca72dbdb0f4fa96fd3ff156d4dbc5b1a222e93`.
Pinned runtime dependencies remain SDAX 0.7.2 and Hamilton 1.90.0. Baseline source
suite: 175 passed on Python 3.12.12 before product changes. This is a local result,
not a new release qualification or claim for other optional profiles.

P0 responsibility map: Hamilton expands declarations; `hamilton_compat` captures
and lowers into the existing NodeSpec mapping; `_types` checks the bounded type
vocabulary; `_selection` and PreparedPlan preserve selected dependencies and
ownership; `_runtime` supplies callbacks to SDAX. Only SDAX schedules retries and
reverse cleanup. No parallel graph authority, generic type system, public modifier
SDK, unbounded snapshotter or Hamilton-specific SDAX API is authorized.

The reviewed plan's trust boundary, explicit optional activation, data-minimal
diagnostics, internal validation roles and finite snapshots are mandatory gates.
Application objects/globals/closures retain identity. Construction executes trusted
Python and is not a sandbox. S must prove capture once per actual mount/context
before broader interfaces freeze. Every new field needs a named consumer.

P1 extends the existing public module fixture with a stock driver oracle and
comparison of names, input/output contracts, optional inputs and selected metadata.
Its characterization tests establish graph/value comparison, no node execution
during construction and original error identity. Family fixtures supply their own
counted construction hooks and synthetic state using the same module factory.
Ownership evidence uses the existing lifecycle suites; do not duplicate them for
every alias. All CI fixtures are public and included by the existing sdist rules.

## Worker assignments

| Lane | Model / reasoning | Initial scope | File ownership |
|---|---|---|---|
| Integrator (root) | Current coordinator | P0/P1, shared contracts, reviews and integration | Shared fixtures, execution ledger, integration changes |
| ham-provenance | GPT-5.6 Sol / high | S feasibility | Composition fixture and feasibility report; no broad P2 admission yet |
| ham-aliases | GPT-5.6 Terra / high | A current-shape aliases/config/metadata | A tests, compiler admission/snapshots, metadata field and compatibility docs |
| ham-pipelines | GPT-5.6 Terra / high | U1 correction | Private pipeline correction helper, tests and correction report |
| ham-loaders | GPT-5.6 Terra / high | U2 correction | Private loader correction helper, tests and correction report |

Use GWZ local clones with the corresponding `codex/ham-*` package branches.
Provision clones serially from a quiet source. Workers never push directly and
commit only their assigned package changes; the integrator serializes family
mutations/merges. Environments and tool caches live outside the source workspaces.
Do not change the shared test environment from a worker.

Expand to at most six editing lanes after S and the shared compiler/binding
foundations pass. Two independent Sol reviewers assess safety and architecture at
integration gates. A correction helper alone does not qualify the entire related
decorator family. Record unsupported combinations explicitly; only gate evidence
can change public compatibility claims.

## Progress

| Task | State | Evidence |
|---|---|---|
| P0 | Complete | Reviewed-plan requirements mapped to existing implementation above; bounded initial ownership assigned |
| P1 | Complete for initial lanes | Four new oracle characterizations pass; full source suite 179 passed on Python 3.12.12; changed fixtures pass Ruff |
| S | Passed bounded feasibility gate | Independent safety and architecture reviewers approve P2/P3; proof commit `827cda8`; production selection/ownership enforcement remains P4/E |
| A / QA | Bounded gate passed | Initial implementation `326c18e`; P2 public-Driver regression closes construction-log sentinel finding |
| U1 | Complete as inactive correction | `20c332a`; upstream expansion delegated, async source preserved; C admission still pending |
| U2 | Complete as inactive correction | `d9c3c81`; exact admitted LoadFrom collection required after the compiler version gate; F admission still pending |
| P2 | Passed bounded foundation gate | `24f7787`; both independent reviewers pass single-resolution capture, nested mount handoff and construction disposal; no broad family activation |
| P3 | Passed bounded gate | `76a5d56`; both independent reviewers pass; original consumer requirements use existing selection/runtime paths |
| P4 | Integrated, bounded gate passed | `d9a80df` merged at `fbc9c69`; both reviewers pass ownership traversal, replacement restrictions, validation roles and concrete default injection |
| B / C / D0–D3 / E / F | In progress | Six editor lanes; helpers and real Driver qualification precede public activation |
| QB onward | Planned | Follow the reviewed DAG; no early activation of unqualified families |

Initial local clones are ready: `ham-provenance`, `ham-aliases`, `ham-pipelines`
and `ham-loaders`, each on its matching `codex/ham-*` member branch. S started from
the checkpoint; the other lanes include conformance foundation commit `f9dd0c2`.
GWZ 1.0.14 does not implement dry-run family merges; integration therefore reviews
committed diffs before using the normal coordinated merge. A dirty member is
rejected, so review records are committed before importing worker changes.

S reviews: [safety](Provenance-Feasibility-ReviewA6a.md) and
[architecture](Provenance-Feasibility-ReviewA6b.md). Their original frozen hashes
remain recorded. The author subsequently strengthened the failure/role/count
witnesses and clarified pinned assumptions; these refinements do not broaden the
bounded gate decision or activate the demonstrated decorator families.

Integrated checkpoint `a154bf4` contains S, A, U1 and U2. All 208 tests pass on
Python 3.11, 3.12 and 3.13 in the existing external release environments; the
Python 3.11 package/authoring mypy check passes. Reviews are recorded in
[A safety](Phase-A-Qualification-ReviewA6a.md),
[A architecture](Phase-A-Qualification-ReviewA6b.md),
[correction safety](Corrections-ReviewA6a.md) and
[correction architecture](Corrections-ReviewA6b.md). Consolidate U1's duplicate
version detector with the enclosing compiler guard when C integrates it.

Two more lanes prepare after S: `ham-validation` (Sol/high) for E/P4, and
`ham-bindings` (Terra/high) for B and necessary bounded type additions. They begin
read-only until their local clones are ready. Existing pipeline/loader workers
continue into C/F; the provenance worker owns shared compiler integration. This
keeps two Sol and four Terra editing lanes, plus independent Sol reviewers.

Both additional clones are ready at checkpoint `bd69ba4`. The aliases lane takes
the construction-diagnostic correction before D2/D3 qualification: Hamilton's
`resolve_nodes` logs ordinary construction exceptions, including callback payloads.
The correction must preserve exception identity, avoid automatic raw logging, and
avoid global logger changes, copied compilation logic or repeated callbacks. QA is
reopened for this finding; earlier frozen reviews remain historical evidence.

Mypy follows the active interpreter rather than forcing Python 3.11 while parsing
newer-interpreter dependency stubs. The existing CI matrix still checks 3.11–3.13;
this resolves the observed NumPy 3.12-stub parse failure without changing runtime
dependencies or the package's Python minimum.

The isolated base-profile regression also identified a necessary precision change:
Hamilton probes Pandera during modifier import even after registry autoload is
disabled. The architecture reviewer accepted documenting this trusted upstream
import behavior rather than adding a global import filter or fork. Frontend
backend activation remains explicit; metadata never activates Ray or caching.
The test isolates unavailable optional packages and separately asserts the pinned
Pandera probe and absence of Ray import requests. This does not claim that ambient
installed validator packages are never imported by Hamilton.

Checkpoint `bc873ea` incorporates the bounded TypedDict checker and independent
C/F/E construction helpers. All 251 tests pass on Python 3.12; Ruff and full
package/authoring mypy on Python 3.11 pass. These helpers do not admit their
decorator families. The TypedDict checker preserves the existing union rules and
rejects structural equivalence between distinct TypedDict declarations.

P2's production capture gate additionally requires nested namespace role
preservation, per-mount resolver counts, finite metadata copies, and disposal after
both successful and failed construction. Its public configuration-predicate
regression must close the reopened construction-diagnostic QA finding. Explicit
public shutdown targets remapped to transformed acquisition nodes remain an E/P4
activation requirement, separate from this bounded foundation gate.

Checkpoint `499b823` integrates P2's production capture with P3, construction
exception transport and bounded TypedDict checking. All 255 source tests pass on
Python 3.12 and the package/authoring mypy check passes. Independent foundation
reviews are recorded in [safety](Compiler-Foundation-ReviewA6a.md) and
[architecture](Compiler-Foundation-ReviewA6b.md). The public configuration-predicate
test preserves the original exception, calls it once and leaves Hamilton's raw
construction logging silent; the reopened A/QA issue is closed.

P4's worker checkpoint has 277 passing tests. Both reviewers independently reran
the suite, Ruff and direct role/ownership tests; the safety reviewer additionally
cancelled a borrowed alias and observed one owner release with the original caller
cancellation preserved. A maintained borrow-specific cancellation composition
case belongs to QB. Family admission, raw target remapping and full Hamilton
validation diagnostics remain separate gates.

Checkpoint `9a0d19a` also incorporates selected pipeline-step contract validation
from `c07e2f9`; all 282 integrated tests pass. Two direct helper tests now use the
existing construction exception boundary, since calling Hamilton directly would
observe the private transport exception rather than the restored original error.

The maintained projection/cancellation composition test exercises real Hamilton
expansion, a generated borrow edge, an async downstream consumer and SDAX cleanup.
It verifies that the owner stays live until cancellation, receives one populated
release, and preserves the caller's cancellation message. This closes the P4
reviewers' requested cancellation regression; broader QB composition remains open.

Compiler file boundaries were reviewed using the split-files guidance. Defer
relocation while family hooks are changing the same declarations; revisit at the
first stable hook checkpoint. Capture/copy lifecycle machinery is the cohesive
candidate boundary. Do not introduce another graph representation or split solely
to satisfy a line count.

Disk pressure briefly prevented pytest from creating temporary files. The six
clones' 2,285-file upstream scratch trees were hash-identical to the root reference;
they now link to that read-only reference instead of keeping duplicate copies.
Product repositories remain independent GWZ local clones. Only regenerable mypy
caches and these duplicate scratch copies were removed. Tests subsequently resumed.

Checkpoint `08be6fb` includes the independently reviewed generated-node capture
hooks and the recursive discovery helper. The preceding `995c364` checkpoint
passed 312 tests on each of Python 3.11, 3.12 and 3.13. The newer checkpoint passes
320 tests on Python 3.12; full lint passes, and integration typing fixes restore
the package/authoring mypy check. These are foundation results, not family admission.

Capture/copy machinery now lives in `_hamilton_provenance.py`; admission,
declaration validation and lowering remain in `hamilton_compat.py`. Both reviewers
approved this cohesion boundary without another graph representation. Production
family work is now distributed across six independent GWZ clones: Sol owns shared
contract transport and optional column capture; Terra lanes own binding/extraction,
pipeline, recursive/model/resolver, and loader/saver hooks; the second Sol lane
owns validation and its optional representations. Method ownership permits these
lanes to edit their distinct hooks concurrently. Root serializes GWZ commits and
merges, then checks compositions before widening public admission.

Checkpoint `edb3bf2` merges C's reviewed selected-step contract capture. Its 22
Driver cases use an explicitly temporary, finite admission harness while QB is
closed; the public allowlist is unchanged. The complete integrated suite passes
341 tests with one opt-in Spark module skipped, plus lint and package/authoring
mypy. Both [pipeline safety](Pipeline-Qualification-ReviewA6a.md) and
[pipeline architecture](Pipeline-Qualification-ReviewA6b.md) reviews record the
required-wins default fix and preserved conjunctive consumer requirements. The
redundant U1 version probe is removed in favor of the enclosing compiler guard.
QB must remove all such provisional admission harnesses and run public Driver
construction before changing the compatibility claim.

CI now isolates five optional profiles on Python 3.12 using pinned test extras.
The Spark job installs a full Java 21 runtime and keeps its Pandas 2 environment
separate from the Pandas/Pandera 3 profiles. These jobs provision qualification;
their presence does not certify unintegrated family implementations.
