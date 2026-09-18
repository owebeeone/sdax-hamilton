# Development documents

Created: 18 September 2026.

| Document | Purpose |
|---|---|
| [Implementation status](Implementation-Status.md) | Current package scope, completed validation and remaining release gates. |
| [Current API](../docs/API.md) | Implemented alpha API and lifecycle contracts. |
| [Compatibility](../docs/Compatibility.md) | Exact admitted declarations, type checks and limitations. |
| [Decorator support plan](Decorator-Support-Plan.md) | New phased roadmap and dependency DAG for all shipped Hamilton decorators; parallel GWZ local-clone procedure. |
| [Coverage execution](Coverage-Execution.md) | Active worker assignments, baseline qualification and implementation gate evidence. |
| [Safety review A6a](Decorator-Support-Plan-ReviewA6a.md) | Independent safety review, first-pass findings and secondary assessment. |
| [Architecture review A6b](Decorator-Support-Plan-ReviewA6b.md) | Independent code-minimization review, first-pass findings and secondary assessment. |
| [Decorator inventory](Decorator-Support-Inventory.md) | Pinned decorator/helper/plugin inventory, confirmed upstream defects and implementation risks. |
| [Machine-readable work DAG](decorator-support-dag.json) | Task IDs, ownership roles, prerequisites and release-readiness gates. |
| [SDAX core execution proposal](../../sdax/dev-docs/Core-Execution-Contracts-Proposal.md) | Separate proposal for cancellation outcomes, backpressure and owned external work; optional workspace-member reference, not a prerequisite for static decorator support. |
| [Release review 0.1.0](release-review-0.1.0.md) | Independent implementation review, concrete findings and regression coverage. |
| [Releasing](../docs/Releasing.md) | Artifact qualification and PyPI trusted publishing procedure. |
| [API design](API-Design.md) | Architecture, proposed declarations, execution and ownership semantics, supported subset, and unresolved contracts. |
| [Implementation plan](Implementation-Plan.md) | Ordered milestones, acceptance checks, compatibility work, evidence handling, and release gates. |
| [Adversarial review A6](api-design-review-A6.md) | Prioritized design findings, concrete failure scenarios, source evidence, and acceptance gates. |
| [Executed frontend comparison](frontend-comparison-results.md) | Parallel Hamilton/native prototypes, shared lifecycle tests, retained failures, and the resulting architecture recommendation. |

## Established direction

- Keep Python SDAX minimal and in its own repository/package. Context-passing
  callbacks and lifecycle execution are intentional core abstractions.
- Keep this frontend in its own repository/package. It depends on `sdax` and
  `apache-hamilton`; SDAX has no dependency on this package or Hamilton.
- Reuse actual Hamilton declarations for a tested subset, preserving their names,
  signatures and graph-construction behavior. Add SDAX-specific declarations in
  the `sdax_hamilton` namespace.
- Translate the entire selected graph into SDAX tasks. Do not run one nested SDAX
  invocation per node under Hamilton's scheduler.
- Prepare reusable execution plans; isolate context and acquired resources per run.
- No core API change, maintained Hamilton fork, or claim of full Hamilton
  execution compatibility is justified by the current evidence.

The original design and comparison documents retain their historical proposals
and evidence. The current API guide and implementation status describe the alpha
implementation and supersede those proposed signatures where they differ.

## Evidence basis

The 17 September investigation used Python SDAX working package bytes at commit
`e178637c4f577eadaa33af0c7fe10524b6183918` and Hamilton source snapshot
`d55da91947da4a8036e35c8ed452e95b01028a09`. These identify source baselines, not a
validated pair of published distribution versions.

- Expanded probe: 50/52 cases passed with unchanged product sources.
- Both failures shared a Hamilton async output-pipeline construction defect.
- An isolated candidate Hamilton correction produced 52/52 passing cases.
- Removing dependency edges or cleanup callbacks caused all five selected
  assertions in each negative control to fail.
- SDAX's source/API and the original Hamilton snapshot were unchanged.
- The prototype rebuilt a translated SDAX processor per call. It did **not**
  implement persistent prepared-plan reuse or establish performance figures.

Workspace-local references, available when this repository is checked out in
`sdax-wz`:

- [Feasibility report](../../HAMILTON-FRONTEND-FEASIBILITY-2026-09-17.md).
- [Campaign and frozen runs](../../sdax-core-evidence/campaigns/hamilton-frontend/README.md)
  — **private evidence member; access required**.

The references are optional research context. A standalone checkout and public
CI must not require the workspace root, scratch snapshot, or private archive.
