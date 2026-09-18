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
| A | Under QA review | Alias/config/metadata implementation `326c18e`; 190 tests, Ruff and mypy pass in its clone |
| U1 | In progress | Pinned source analysis; isolated correction follows clone readiness |
| U2 | In progress | Pinned source analysis; isolated correction follows clone readiness |
| QA onward | Planned | Follow the reviewed DAG; no early activation of unqualified families |

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
