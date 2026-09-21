# Static Hamilton coverage implementation review — A6b

## Verdict

The frozen code-complete snapshot at
`e0093b54147733cec5bd8fdef4bb03cd7f6e3163` does **not** pass the final release
gate. It has two concrete blockers. First, its Spark construction guard does not
reject Hamilton loader or saver effects connected to a caller-owned lazy Spark
plan. Second, its publishing workflow does not require the five optional-profile
installed-wheel runs. Neither finding calls for reopening the compiler or SDAX
runtime architecture.

The root integrator prepared narrow corrections during this review. I inspected
the source diff for both corrections and ran the five new Spark construction
regressions; all passed without starting a Spark session. In that corrected tree,
Hamilton is still used once for construction and native edge validation, the
result is lowered into the existing immutable frontend model, Hamilton's mutable
graph state is discarded, and SDAX remains the sole runtime scheduler and cleanup
authority. The corrected tree has no remaining architecture or code-minimization
stop from this bounded review. No push, release or publication is approved by
this review.

The principal reviewed source hashes are:

- `hamilton_compat.py`:
  `0163fa934cb4a2e1aab46324377da0c0506d77108e2efef2a27304e25831e98b`
- `_hamilton_provenance.py`:
  `27ad2452f3489ef92a93e8ad95e8298feeb41167236091dcdb90d184ae5d4d13`
- `_hamilton_bindings.py`:
  `7b23d2a9ac39562e9de860578d307619efa0a181233d4675e80de87a2ccaee0a`
- `_hamilton_pipeline.py`:
  `1f10424354856a4da2fd4aeedf7a343c5c2632a17e3d07a6bc723a62068e45d1`
- `_optional_profiles.py`:
  `7c5891eb5ea0635df6b69e35b5be92eefe6340f4205b5d9971364b71ecc028ab`
- `_hamilton_validation.py`:
  `0eade18e115d97ab55610ddd15aa63807f52a038b942940723775bd83d8ae9da`
- `_hamilton_spark.py`:
  `64598a9f41e1ed4615cc6d370bf8a6bfcdd405ec7f120256c444b1b492001c06`
- `_runtime.py`:
  `013e4e96b27bf47267ad9d955bea60b77b18f83cab3a9314c8dcb597aea2de35`

The supplied qualification evidence for the frozen snapshot reports 434
installed-wheel tests passing on each of Python 3.11, 3.12 and 3.13, plus passing
installed-wheel runs for all five optional profiles. Those runs did not contain
the missing F×G3 negative cases. For the corrected tree, the root integrator
reported 435 installed-wheel tests passing on each of Python 3.11, 3.12 and 3.13,
453 Spark-profile installed-wheel tests passing under isolated import, and the
remaining optional profiles, lint and type checks passing. I did not repeat those
full matrices. I inspected the final root sources and tests directly, ran one
targeted Spark/config construction reproduction, and ran the five new connected
I/O regressions. Both targeted runs completed without starting a Spark session.

## Concrete finding

### Production blocker at `e0093b5`: Hamilton I/O could cross the Spark boundary

The independent safety reviewer found and reproduced this defect. In the frozen
snapshot, `reject_unsafe_spark_cones()` at
`src/sdax_hamilton/_hamilton_spark.py:9-45` walks only ancestors of exact Spark
nodes and checks ownership, release, borrowing and policies. Hamilton loader and
saver effect nodes are deliberately represented without declaration acquisition
ownership, so these checks do not identify the I/O effect itself. The guard also
does not walk descendants. Consequently, a loader can feed a Spark decorator and
a direct or indirect saver can consume its lazy result. The caller-owned lazy
Spark profile cannot safely claim either composition.

Nested I/O had a second route. The frozen `chain_with_capture()` at
`src/sdax_hamilton/_hamilton_provenance.py:1051-1062` passes generated helper
nodes into Hamilton's native `chain_subdag_nodes()` without first rejecting an
I/O helper. This permits a nested data loader to reach native Spark UDF
combination before the final lowered-graph guard can establish the intended
boundary.

The root's correction is appropriately narrow:

- `_hamilton_spark.reject_spark_io()` recognizes only Hamilton's reserved
  `hamilton.data_loader` and `hamilton.data_saver` boolean tags.
- The existing upstream-cone walk calls that check for every ancestor.
- A construction-local reverse adjacency over the existing `NodeSpec.inputs`
  checks direct and indirect descendants for saver effects while allowing an
  independent I/O branch that merely shares an ordinary external input.
- The exact Spark `with_columns` hook checks generated helper nodes before
  delegating to native `chain_subdag_nodes()`, closing the nested-loader route
  before native UDF combination.

This adjacency is a discarded validation index over the already lowered specs;
it does not become another graph model, executor or runtime authority. It adds no
persistent model field and no runtime branch. The reviewed corrected hashes are:

- `_hamilton_provenance.py`:
  `bc8a63d5ec796ece4480bc94006d2c2f97799821f693b65c2a09b4e89691b032`
- `_hamilton_spark.py`:
  `bef3373dd82a63e8d28a41bf4164116aecdccdb4afc1046f960498a009be62c6`
- `tests/test_spark_driver_profile.py`:
  `4797b46fce16c34be46e516d575378db7ed0b962ab6da172894f92219b4c8fe7`

I ran the five focused public regressions covering an upstream loader, a direct
saver with a timeout policy, an indirect saver, an accepted independent I/O
branch, and a nested loader. They passed (`5 passed, 8 deselected`). Each negative
case also asserts that adapter construction did not occur and that no Spark
context was created. This closes the production blocker for the documented exact
Hamilton I/O decorators and bounded Spark profile.

### Release blocker: optional profiles were outside the publish dependency graph

At `e0093b5`, `.github/workflows/publish.yml:49-92` tested the built wheel only
with the base test extra, and its `publish` job at lines 94-96 depended only on
`build` and `test-wheel`. The optional profile matrix lived in the separate
`.github/workflows/tests.yml:32-57` workflow. A version tag could therefore reach
the PyPI job even if Pandas, Polars, Pydantic, Pandera or Spark qualification had
failed or had not run for the exact artifact being published. That did not satisfy
the plan's packaging gate.

The correction is confined to the release workflow. The reviewed diff extends
the same built-wheel job with Python 3.12 entries for all five pinned profiles,
installs the matching wheel extras, provisions Java only for Spark, and retains
`publish`'s dependency on the whole `test-wheel` matrix. Its reviewed hash is
`b6757288b0221d3db00d945c85cd57c81fe79b629c7ff10dddc6f86a3b602ce0`.
The reported artifact matrix passed. This correction does not justify production
code changes.

## Compiler and runtime architecture

`compile_modules()` in `hamilton_compat.py:384-565` is still the single frontend
compiler path. It checks the pinned Hamilton and SDAX versions, discovers and
validates declarations, invokes the captured Hamilton resolver once for each
actual declaration context, attaches ownership and policy facts, and lowers each
resolved node directly to `NodeSpec`. The only graph operation after lowering is
Hamilton's native `graph.update_dependencies()` at lines 556-562 for its edge
compatibility checks. That mutable graph does not escape the function and no
Hamilton executor or lifecycle adapter runs at application runtime.

Construction exception transport in `_construction.py:30-61` wraps only copied
modifier lifecycle methods, delegates to Hamilton, and restores the original
exception and traceback outside Hamilton's payload-formatting logger. It does not
patch a process-global logger or copy Hamilton's resolver algorithm.

The immutable `NodeSpec` mapping feeds `_selection.select()` and
`_runtime.build_processor()`. Selection validates the chosen dependency cone,
config, overrides, original merged requirements, protected validation nodes and
ownership before effects (`_selection.py:49-178`). Runtime construction creates
only SDAX `AsyncTask` call/check pairs and SDAX post-execute shutdown callbacks
(`_runtime.py:91-118`). Retries and timeouts come from the one frontend `Policy`
object passed to SDAX; Hamilton cache and Ray tags remain inert metadata. I found
no parallel executor, replay path, duplicate runtime graph or second policy
authority.

## Provenance, ownership and generated metadata

The construction-local `_CapturedFact` has a concrete consumer for every field.
Role controls validation selection and replacement, declaration/public name/mount
control policy and shutdown target mapping, `actual_call` and `borrows` control
ownership, `input_contracts` feed `_lower_inputs()`, and `policy_target` admits
only explicit synthetic I/O policy targets. The facts are keyed by exact callable
identity within an exact mount. Namespace handoff checks node count, ordered input
types and the pinned Hamilton 1.90 rename behavior before remapping contracts
(`_hamilton_provenance.py:169-249`). Capture methods and identity tables are
restored and cleared in `finalize()` at lines 1336-1351 on both success and
failure.

Recursive construction delegates the saved native `collect_nodes()` for one
actual source at a time while tracking the original declaration as active
(`_hamilton_provenance.py:131-167`). This retains native resolution and tagging,
rejects delayed recursive cycles, and permits acyclic sibling reuse. Subdag and
optional-column namespace hooks delegate their saved Hamilton methods, then
correlate the exact returned nodes through the same handoff. They do not infer
roles from generated names or build another graph.

Generated validation raw/evidence/gate roles remain non-bypassable. Loader and
saver hooks identify the pinned returned shapes and tags, retain Hamilton's
selected adapter factory, and create adapter instances only inside the SDAX-timed
callback. The construction-only `policy_target` passes through transformations
that preserve the raw effect identity; projections and validation gates do not
become independent effect targets. Borrow traversal starts from same-owner
borrowing aliases, so public projections can reach their actual acquisition while
fresh SaveTo metadata cannot masquerade as a shutdown alias.

`NodeSpec` snapshots the tag mapping and Hamilton-supported list-valued tag
containers while retaining application values by identity. This matches the
documented shallow-state boundary: defaults, literals, globals, closures, models,
validators and adapter state are trusted application objects rather than inputs
to a universal object copier.

## Bindings and helpers

`_hamilton_bindings.py` is the sole authority for source, value and group binding
capture. It snapshots the finite Hamilton dependency containers, retains every
original consumer requirement in the existing `InputSpec`, treats any required
consumer as making a merged source required, and retains an optional default only
when all candidates are the same object. Configuration renames and generated
projection names are correlated against the exact nodes returned by Hamilton;
loss and collision fail during construction.

Pipeline selection still delegates `Applicable.bind_function_args()` after
Hamilton chooses the active step. Literal checks and `selected_step_input_contracts()`
consume that one native binding result, so there is no second selector or pipeline
interpreter. Plain helper code/defaults are copied once per Driver, external helper
policies and shutdowns are discovered by exact function identity, and callable
instances fail at the documented plain-function boundary.

There is one optional simplification at this seam. The selected step's
`_function_contract()` is evaluated by the installed bound-step preflight at
`_hamilton_pipeline.py:273-282,324-347` and then again by
`selected_step_input_contracts()` at lines 285-321, reached from
`_hamilton_provenance.py:649-659`. This duplicates signature and
`get_type_hints()` evaluation for the selected helper. It is not a release blocker:
annotations are trusted construction code, no node callback or selector is
replayed, and the qualified cases are deterministic. If this seam changes later,
one helper can return the validated contracts alongside the native binding result.
Do not add a global cache, new binding representation or framework solely for
this cleanup.

## Optional profiles

Optional activation is minimal and explicit. `_optional_profiles.py:36-46`
matches the exact class object from an already loaded shipped module by reading
the module dictionary directly. It does not import a backend, call module
`__getattr__`, scan a registry or add a second Driver profile setting. Profile
versions are checked only after an admitted modifier selects that profile.

Pydantic and Pandera reuse the common validation expansion. Their correction
changes only the generated runtime representation while retaining the original
annotation for Hamilton's validator construction. Pandas/Polars/Spark column
hooks reuse native `with_columns` expansion and the common namespace handoff.
Experimental `parameterize_frame` reuses the ordinary B binding capture rather
than maintaining a profile-specific contract map.

Spark's corrected guard is construction-only and narrow. It walks the already
lowered upstream cone of exact Spark nodes and rejects ownership, borrowing,
shutdown, nondefault policies and Hamilton I/O effects before callbacks. Its
ephemeral descendant index detects direct and indirect savers, and the captured
native generated-node boundary rejects nested I/O before Spark UDF combination.
It does not schedule Spark, copy a Spark plan or persist another graph. The
documented classic-local, caller-owned, lazy-plan boundary remains material:
Spark decorators inside Hamilton subdags, standalone `require_columns`, nested
UDF lifecycle state, Spark Connect, background work and timely cancellation of
blocking actions are outside the claim.

## Code-minimization disposition and limits

`_hamilton_provenance.py` is large, but line count alone is not a reason to split
it now. Its hooks share the same callable identity map, mount stack, pending facts,
method restoration and finalization lifetime. Moving individual hooks while those
facts remain shared would either add forwarding wrappers or risk a second state
authority. A later split is justified only if pure per-family shape/snapshot
functions can move without relocating or duplicating construction state. No broad
rewrite is recommended for this release gate.

This review covers the documented static allowlist and its explicit restrictions,
not every possible composition of Hamilton decorators. It relies on the exact
Hamilton 1.90.0 and SDAX 0.7.2 pins and the stated optional dependency versions.
Construction executes trusted Python and is not a sandbox. Mutable application
objects retain identity and must meet the caller's concurrency contract. The
Spark restrictions above and the trusted SaveTo metadata non-alias contract are
real compatibility limits rather than future-coverage defects.

The campaign DAG/status prose contains historical intermediate states. It should
be annotated as historical or updated to the final bounded statuses without
claiming unrestricted Hamilton support. The root's installed-source AST
import-boundary regression is useful hardening for disabled branches, but it does
not require another compiler layer. Its reviewed test-file hash is
`a6e37e52e9895a1627cc781fa05e9f517cf2be67734f2cb326c03d9863f095a9`.
With the Spark and release-workflow corrections applied and the reported artifact
checks passing, this review has no remaining architecture or code-minimization
stop.
