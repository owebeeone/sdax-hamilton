# Hamilton decorator support inventory

Investigated 18 September 2026 against installed `apache-hamilton==1.90.0`.
Frontend baseline: `sdax-hamilton` v0.1.0, commit `2ef785a`; SDAX `0.7.2`.
This is a planning inventory, not a claim that the entries below are supported.
Execution plan: [Decorator-Support-Plan.md](Decorator-Support-Plan.md).

## Scope and meaning of complete

Cover every shipped public decorator in this Hamilton version: main exports,
public submodule factories, plugin decorators and the experimental decorator below.
Retain exact upstream import paths and signatures. Preserve upstream errors for
forms that Hamilton itself rejects. Test supported arguments/compositions, not
just successful imports. Future Hamilton versions require a new inventory diff.

Registered loader/saver implementations are an open registry, not a finite list
of decorators. Test the adapter protocol and representative installed adapters;
identify individually qualified optional integrations. Arbitrary third-party
decorators require the extension contract in phase X, not a universal claim.

Support has separate dimensions: declaration expansion, ordinary execution,
async behavior, policy/ownership composition, and optional backend behavior.
Preserving a `cache` tag does not implement caching. A family is only marked
supported for combinations that pass its conformance and lifecycle gates.

## Shipped decorator families

Paths in the source column are relative to the installed `hamilton/` package.
Phase IDs refer to the plan and its machine-readable dependency graph.

| Surface | Public decorators/forms | Implementation and phase |
|---|---|---|
| Configuration | `config(...)`, `config.when`, `when_not`, `when_in`, `when_not_in`; `hamilton_exclude` | `function_modifiers/configuration.py`; A. Four named selectors are already admitted; custom predicates/exclusion need qualification. |
| Parameterization | `parameterize`, `parameterize_values`, `parameterize_sources`, `inject` | `function_modifiers/expanders.py`; A handles convenience forms; B completes binding/composition support. Direct `parameterize`/`inject` already admitted with restrictions. |
| Legacy parameterization | `parametrized`, `parametrized_input`, `parameterized_inputs` | `expanders.py`; A. Preserve upstream deprecation behavior. |
| Extraction | `extract_columns`, `extract_fields`, `unpack_fields`, `parameterize_extract_columns` | `expanders.py`; B. Projection nodes must borrow from the actual owner. |
| Callable replacement | `does` | `function_modifiers/macros.py`; C. Check replacement callable binding, not only placeholder signature. |
| Model generation | `dynamic_transform`, `model` | `macros.py`; D3. Configuration constructs a model/bound compute callable; these are not runtime fan-out. Preserve upstream deprecations. |
| Pipelines | `pipe_input`, `pipe`, `pipe_output`, `mutate` | `macros.py`; C, with U1 async correction gate. Preserve upstream restrictions such as unsupported collapse forms. |
| Metadata | `tag`, `tag_outputs`, `schema.output` | `function_modifiers/metadata.py`; A. `tag` is currently admitted, but the frontend IR does not expose/preserve the full metadata surface. |
| Cache directives | `cache` | `metadata.py`; A preserves declaration metadata; K0 establishes feasibility/trust; K/QK implement and qualify explicitly enabled caching. |
| Ray directives | `hamilton.function_modifiers.metadata.ray_remote_options` | `metadata.py`; A preserves declaration metadata; R0 establishes feasibility/authority; R/QR qualify explicitly enabled remote execution. Not re-exported by the root modifier package. |
| Validation | `check_output`, `check_output_custom` | `function_modifiers/validation.py`; E. Raw result, validation nodes and final result are distinct roles. |
| Recursive composition | `subdag`, `parameterized_subdag` | `function_modifiers/recursive.py`; D0 supplies recursive discovery/mount provenance; D1 completes public options. |
| Deferred resolution | `resolve`, `resolve_from_config` | `function_modifiers/delayed.py`; D2. Resolve once at construction with upstream power-user requirements. |
| I/O | `load_from.<registered-adapter>`, `save_to.<registered-adapter>`, `dataloader`, `datasaver` | `function_modifiers/adapters.py`; F, with U2 generated loader type correction. Include targeting, injection, metadata and custom registration. |
| Pandas | `hamilton.plugins.h_pandas.with_columns` | `plugins/h_pandas.py`; G1 over D0/B. Optional dependency profile. |
| Polars eager | `hamilton.plugins.h_polars.with_columns` | `plugins/h_polars.py`; G2 over D0. |
| Polars lazy | `hamilton.plugins.h_polars_lazyframe.with_columns` | `plugins/h_polars_lazyframe.py`; G2 over D0. Preserve lazy evaluation. |
| Spark | `hamilton.plugins.h_spark.with_columns`, `select`, `require_columns` | `plugins/h_spark.py`; G3 over D0. Qualify an actual local Spark session; SDAX does not schedule Spark's internal jobs. |
| Pydantic validation | `hamilton.plugins.h_pydantic.check_output` | `plugins/h_pydantic.py`; V. Resolve the dict/model contract described below. |
| Pandera validation | `hamilton.plugins.h_pandera.check_output` | `plugins/h_pandera.py`; V. Schema and validation-error compatibility. |
| Experimental dataframe parameterization | `hamilton.experimental.decorators.parameterize_frame.parameterize_frame` | `experimental/decorators/parameterize_frame.py`; G1. Explicit experimental status and separate cases. |

Helpers used by these decorators, not additional decorators: `source`, `value`,
`group`, `configuration`, `ParameterizedExtract`, `step`, `apply_to`, `ResolveAt`.
Also account for exported dependency classes, validation tag constants and
`InvalidDecoratorException` in API inventory checks. `schema` is a namespace;
`schema.output` is its decorator factory. `hamilton_exclude` is a ready decorator
instance. Dynamic loader/saver namespaces are factories backed by registration.

`Parallelizable`/`Collect` are runtime graph annotations, not decorators.
Hamilton drivers, general lifecycle adapters, result builders, UI integrations,
checkpointing and distributed schedulers are separate APIs. Do not silently add
those entire projects to this decorator completion target. K/R explicitly cover
runtime behavior needed by cache/Ray directives; future dynamic-graph work gets
its own design without blocking static decorator releases.

## Review-driven qualification rules

The revised plan evolves existing NodeSpec/checker/selection boundaries; it does
not add a second graph, scheduler or generic type/snapshot framework. A counted
composition slice S proves the provenance seam before P2/P3. A/QA can qualify
simple forms independently; C/F develop unaffected cases before U1/U2 join at QB.

Trusted imports, constructors, decorators and registrations can execute code during
construction. Admission is not a sandbox and cannot undo those effects. Capture
selected adapter identity using upstream precedence; an existing Driver does not
re-resolve a mutated registry. Count resolution once per actual mount/context.

Checked validation keeps generated raw/evidence nodes internal and gates
nonreplaceable through config/overrides. `check_outputs=False` does not disable
Hamilton fail-validation. Default generated diagnostics omit raw payloads; record
this and stricter selection as deliberate frontend differences, while preserving
user exception identity. These are planned policies, not released guarantees.

Z audits static shipped profiles. QK/QR separately gate cache/remote behavior;
ZR audits combined runtime coverage. Metadata alone activates neither profile.
Cache qualification requires explicit storage/deserialization trust and value
eligibility. Remote qualification requires trusted destination/options, one retry
authority and proven stop/join before retry or dependent resource release. K0/R0
may stop those profiles if reuse requires a shadow runtime. Reduced profiles are
never described as full backend parity. X is optional and does not block Z.

## Findings that shape the implementation

1. **Use Hamilton's expansion.** `function_modifiers/base.py:796` resolves config,
   creates nodes, injects dependencies, expands/transforms nodes and applies metadata.
   `parameterize_values` and `parameterize_sources` delegate to `parameterize`.
   Reimplementing these public decorators would duplicate upstream semantics.
2. **Ownership is currently too coarse.** Our compiler assigns
   `ownership_required=fn in owned` to every generated node. A validator or extractor
   would be misclassified as another acquisition. Hamilton's `originating_functions`
   gives ancestry, not ownership. The new representation must distinguish both.
3. **Nested validation cannot stop at top-level functions.** `subdag.collect_nodes`
   recursively resolves embedded declarations. Pipeline steps, delayed decorators,
   nested shutdown declarations and plugin subgraphs require recursive admission
   and snapshots before invoking expansion.
4. **`mutate` has already run at import time.** It edits target functions' output
   pipelines and excludes the mutator. Preserve upstream same-module restrictions.
   Snapshot the resulting graph and helper references; do not expect to find a
   `mutate` lifecycle instance later. Exclude helpers before node-signature checks.
5. **Helper scope matters.** In 1.90.0, `configuration(...)` is consumed by subdag
   configuration resolution, not generic `parameterize`/`inject` binding.
   `group` admits direct source/value elements; do not invent nested/config forms.
6. **Generated raw types need checking.** `dataloader` generates a raw tuple node
   and a projected data node. `datasaver()` requires a literal `dict` return
   annotation in the inspected version; some generic/postponed forms fail upstream.
7. **Pydantic has a deliberate contract conflict.** Its decorator permits a dict
   returned under a model annotation. Strict nominal model-instance checking does
   not describe that behavior. V must distinguish schema validation from runtime
   representation and reject unsafe downstream model-instance assumptions; neither
   globally disable checks nor silently coerce values to advertise compatibility.
   The qualified producer and shutdown type is therefore
   `Model | dict[str, Any]`; a nominal `Acquisition[Model]` shutdown is rejected
   because the raw acquisition may be a dictionary. Pandera validation advertises
   the concrete `pandas.DataFrame` runtime representation. Its qualified shutdown
   uses that concrete class; generic `DataFrame[Schema]` consumer and shutdown
   annotations remain unsupported until schema-aware edges are separately proven.
8. **Snapshot bounded metadata, preserve application state.** Models, validators,
   adapters and captured literals can hold mutable state. Own immutable binding
   metadata; explicitly document per-driver/per-invocation state and reentrancy.
   Prove concurrent reuse or reject/serialize the specific stateful profile by an
   explicit frontend policy, never change SDAX globally.

## Confirmed pinned-upstream defects

Two in-memory probes used the installed 1.90.0 implementation with bytecode
disabled; no source edits, monkey patches or private fixtures were involved.
Convert these triggers into maintained public regressions in P1/U1/U2.

- **U1, async output pipeline:** resolving an async function decorated with
  `pipe_output(step(a_typed_sync_step))` raises `ValueError` for a missing return
  annotation on `pipe_output.transform_node.<locals>.async_function`. Source also
  awaits a synchronous identity result; that second defect is a source finding
  behind the observed construction failure and still needs an execution test.
- **U2, loader node type:** a compliant in-memory integer loader returns
  `(7, {"source": "memory"})`. `LoadFromDecorator.get_loader_nodes("item", int)`
  declares `tuple[dict[str, Any], int]`; its projection selects element zero as
  `int`. Our structural value check rejects the incorrectly annotated raw tuple.

Prefer a narrowly versioned compatibility correction or a tested upstream upgrade.
An upgrade requires re-inventory and regression qualification. Do not waive type
checks, patch installed packages globally, or fork Hamilton to unblock everything.
Upstream communication is separate from implementing these local corrections.

## Sources and provenance

Primary evidence is the installed 1.90.0 source, especially
`function_modifiers/{__init__,base,configuration,expanders,macros,metadata,validation,recursive,delayed,adapters}.py`
and the plugin/experimental modules enumerated above. Local inspection used the
release qualification environment described in [Implementation status](Implementation-Status.md).
This environment is an investigative convenience, not a public CI prerequisite.

Official references (rolling documentation; pinned source wins on disagreement):
[function modifiers](https://hamilton.apache.org/concepts/function-modifiers/),
[decorator reference](https://hamilton.apache.org/reference/decorators/),
[dynamic execution](https://hamilton.apache.org/concepts/parallel-task/).
