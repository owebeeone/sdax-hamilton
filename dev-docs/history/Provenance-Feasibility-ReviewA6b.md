# Compositional provenance feasibility — independent architecture review A6b

Date: 18 September 2026. Scope: plan task S, architecture, provenance fidelity,
product-code minimization and the proceed/stop gate for P2/P3.

Frozen inputs:

- `tests/test_provenance_feasibility.py` SHA256
  `061eefab567cfa0023c5a57e4b4971ad981244ef46da3361c6eeaf28598a34a8`
- `dev-docs/Provenance-Feasibility.md` SHA256
  `f7010491a3f8cf121f0d1c2c1ac81a3133fd44e4bb3be1b00c49a3a869d835c1`

This review is independent of other S reviews. It changes no product source,
feasibility test, feasibility report, workspace configuration or evidence archive.
Workspace `AGENTS.md`, `AGENTS_GWZ.md` and `EVIDENCE.md` were read. The governing
plan and its reviewed architecture goals were inspected. No GWZ command, install,
network operation or evidence-campaign mutation was performed.

## Verdict

**Proceed to P2 and P3 for the bounded S slice.** The proof establishes a viable
local interception seam for the hard composition without replaying Hamilton's
compiler, parsing generated names, patching process-global objects or adding an
alternative runtime graph. P2 may now evolve the existing `NodeSpec` lowering,
and P3 may extend the existing bounded binding/type checks. This verdict does not
qualify P2, P3, P4, recursive public subdag support, delayed decorators generally,
validation policy or any decorator family beyond this feasibility fixture.

The frozen proof has no stop finding. Three nonblocking findings below constrain
how P2 turns the test-local probe into product code and how the report should be
read. In particular, the report's short version-coupling list is not exhaustive,
and the proof captures the roles needed by this slice rather than every node role
created by a parameterized subdag.

## Why the gate passes

The fixture is the required composition rather than a surrogate. Two declared
`parameterized_subdag` mounts each contain a real SDAX acquisition/shutdown pair,
an `extract_fields` projection and a delayed resolver returning Hamilton's
validation modifier. The captured build calls Hamilton's real `resolve_nodes`
once at its outer boundary. Recursive collection remains Hamilton-owned.

The probe clones the finite declaration/modifier containers and instruments only
the clones and the new per-mount `subdag` generator instances. It delegates the
upstream projection, validation, delayed resolution and namespace operations.
The original declarations, original modifier instances and global
`base.resolve_nodes` object remain untouched. A prepared Driver constructed before
the probe still executes afterward. The separate stock graph and Driver are test
oracles; neither is an authority used by the captured SDAX execution path.

Role classification is based on exact objects returned at the pinned family seams.
`extract_fields` output position supplies projection source/projection roles;
`BaseDataValidationDecorator` output position supplies validator/gate/raw roles;
the delayed wrapper records the actual copied resolver and returned modifier type;
and acquisition is linked to the original declaration carrying the SDAX release.
Generated spelling is used only to key/assert results after classification, not to
decide a role. The test also demonstrates why final validation ancestry cannot
replace this capture: raw, validator and gate nodes have the same ancestry.

The delayed callback count is two for the captured construction and the recorded
mount counts are exactly one for `low` and one for `high`. Stock construction has
the same count. The normal Hamilton graph and captured graph agree on generated
names, output types and dependency mappings, while stock Hamilton and lowered
SDAX execution agree on values. Both successful and failing validation executions
acquire and release each mounted resource exactly once. Owner traversal from each
checked node reaches only its same-mount acquisition.

Lowering feeds the existing `NodeSpec`/`PreparedPlan` path. No Hamilton scheduler,
retry loop, cleanup walker or retained `FunctionGraph` is introduced. The proof's
test-local lowering is deliberately incomplete product code, but it is sufficient
to show that real acquisition nodes can receive releases while projections and
validation nodes do not. P4 still owns selection, replacement, escape and full
lifetime behavior.

## Findings

### M1 — Medium: the documented version-coupling list is incomplete

**Anchors:** feasibility report lines 78–86; test lines 220–267 and 273–322.

The report names `_gather_subdag_generators`, the namespace operation and the
ordered results of `extract_fields` and `BaseDataValidationDecorator`. Those are
real dependencies, but they are not all of the pinned assumptions used by the
probe.

The capture also relies on these Hamilton 1.90.0 behaviors:

- `parameterized_subdag.load_from` exposes the declarations that recursive
  collection will use, and copied modifier instances remain independently
  instrumentable;
- `_gather_subdag_generators` returns mutable `subdag` instances with an available
  `namespace`, and their instance methods can be shadowed locally;
- `generate_nodes` performs recursive `collect_nodes` and delayed resolution while
  the wrapper's mount context is active, then calls the wrapped namespace step;
- tagging/copying collected nodes preserves the generated callable identity long
  enough for `_pending[id(entry.callable)]` correlation;
- ordinary/acquisition nodes retain the cloned declaration in
  `originating_functions`;
- namespace conversion is one-for-one and order-preserving, which makes the
  strict positional `zip` a valid pre/post correlation.

The exact 1.90.0 pin and the frozen test make these assumptions acceptable for S,
so this is not a stop. P2 must put the complete set inside the existing private,
fail-closed compatibility boundary. Its regression should fail loudly if callable
identity, ancestry, mount-time sequencing, cardinality or positional correlation
changes. The public report should either enumerate these assumptions or describe
its current list as examples rather than the complete version-coupled surface.

### L1 — Low: the witness proves the required roles, not a complete mount census

**Anchors:** test lines 281–317, 333–348 and 489–499; feasibility report lines
41–44 and 104–116.

The probe records provenance for nodes collected before namespacing. It explicitly
asserts acquisition, projection and all three validation roles for the `low`
mount, and it proves same-mount owner reachability for both `low` and `high`.
The delayed-resolution census covers both mounts. That is enough for the bounded S
acceptance criterion because both mounts use the same generated family path.

It does not assert a complete role map for the `high` mount. It also does not add
provenance for the parameterized subdag's generated static-input node or final
mount-output node, which are created after the wrapped namespace operation. The
final output still retains its owner through ordinary dependency traversal, so
this omission does not invalidate the demonstrated lifetime path.

P2 should avoid turning this into a demand that every generated node receive a new
role field. First name the selection, ownership, policy or diagnostic consumer.
For roles that do have a consumer, add an exact two-mount role census, including
the projection-source role, and assert that no expected captured node is missing or
duplicated. If mount-final/static provenance is needed for a named consumer, add a
specific capture seam and witness then; otherwise preserve the smaller model.

### L2 — Low: disposal is an implementation constraint, not directly proved here

**Anchors:** feasibility report lines 7–13 and 75–76; test lines 206–213, 324–349
and 467–533.

The report says temporary identity records exist only during lowering and the
Hamilton node collection is discarded after conversion. That accurately states
the required product architecture and matches the current product compiler, but
the feasibility test itself retains `CaptureCompiler`, its `_pending` and
provenance tables, and the `captured_nodes` tuple so later assertions can inspect
them. The SDAX plan does not consult those objects, and no product code changed,
so there is no second runtime authority in this slice.

P2 must make the report's stronger statement true in product code: construction
state must be local to compilation, only demonstrated facts with named consumers
may enter immutable `NodeSpec` data, and the resolved Hamilton collection and
temporary identity indexes must become unreachable after lowering. Do not ship
the test's `CaptureCompiler` as a parallel compiler object merely because it made
the experiment easy to inspect.

## P2/P3 architecture constraints

P2 should extend the current recursive function-copy and `compile_modules`
boundary rather than add another compiler facade. One construction-local capture
context can own mount stacks, identity correlations and exact-family callbacks,
then populate the existing authoritative node mapping. The production change
should share the current snapshot machinery and version check. It should not copy
Hamilton lifecycle ordering, retain a `FunctionGraph`, introduce a scheduler or
expose a public modifier protocol.

Dispatch must remain fail-closed. The fixture's `isinstance` checks are suitable
for a controlled feasibility probe; product admission still needs the plan's
exact supported-family decisions so an arbitrary third-party subclass does not
gain support accidentally. A wrapper/helper is justified only where its captured
fact has a named consumer. Several families may share one small helper; the test's
class layout is not a required product layout.

P3 can proceed independently on the existing `_types` and original consumer
requirements. S confirms that original declaration annotations remain available
through the copied recursive declarations and that generated edge types survive
the capture seam. It does not prove literal/default checking, merged requirement
sets or a broader annotation grammar. Those remain P3/family acceptance work and
must not be inferred from this pass.

P2 and P3 should integrate as one lowering path. Provenance facts must not create
a second binding/type representation, and binding snapshots must not expand into
generic object copying. Globals, closures, literal application values and stateful
validator/model instances retain identity except where a later qualified family
defines a narrower rule.

## Boundaries of this decision

S does not establish nested mount paths, shared/cyclic declaration traversal,
mount-specific dynamic configuration differences, stacked transforms on one
declaration, generated validation selection policy, config/override bypass
protection, ownership escape handling, metadata immutability or registry adapter
identity. It also does not establish packaging or the Python 3.11/3.13 matrix.
These are follow-on qualifications, not reasons to stop P2/P3.

P4 remains the gate for using provenance in ownership retention and policy. Family
work remains responsible for each exact generated-role contract. A later family
whose Hamilton seam cannot satisfy the same single-delegation, local-copy and
fail-closed rules must stop at that family's gate; this S verdict is not blanket
future coverage.

## Verification

The frozen hashes matched the values above. The designated qualification Python
was run with bytecode generation disabled, `PYTHONPATH=src`, and pytest's cache
provider disabled:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider tests/test_provenance_feasibility.py -q
..                                                                       [100%]
2 passed in 0.27s
```

## Post-review disposition

The author supplied a strengthened witness after the frozen review above:

- `tests/test_provenance_feasibility.py` SHA256
  `4f52f311a455fd269039dd8957aef4e77ac83553644c04f52395dd74b34bc95b`
- `dev-docs/Provenance-Feasibility.md` SHA256
  `15d47acda1017655a13c1a6560766b80e27730417aee692412a2ab25dea6ab33`

The strengthened report enumerates the identity, ancestry, sequencing,
cardinality and ordered-result assumptions identified in M1. It explicitly says
the test retains temporary objects for inspection and assigns production disposal
to P2, resolving L2's wording issue. The test now asserts the acquisition,
projection-source, projection, validation-raw, validator and validation-gate roles
for both mounts, rechecks the resolver count after successful execution, and
confirms the failure contains Hamilton's actual `DataValidationError`. This
addresses L1 for the bounded role set without introducing provenance for static or
mount-final nodes that have no named consumer yet.

The strengthened test passed in the designated environment with bytecode and
pytest caches disabled (`2 passed in 0.64s`). The **proceed** verdict is unchanged,
and the original frozen review remains the assessment record. M1, L1 and L2 are
closed by this follow-up for S; their product-facing constraints remain applicable
to P2/P3/P4.
