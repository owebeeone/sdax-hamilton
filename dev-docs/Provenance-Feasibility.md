# Compositional provenance feasibility

Date: 18 September 2026. Hamilton: 1.90.0. SDAX: 0.7.2. Plan task: S.

## Result

The feasibility gate passes for its bounded slice. The production compiler now
captures acquisition, projection and validation roles while delegating each
Hamilton lifecycle operation once. It does not replay `resolve_nodes`, infer roles
from generated names, patch process-global Hamilton objects, introduce a retained
product graph, or change SDAX core. The same lowering path used by public
compilation consumes the capture records and returns only immutable `NodeSpec`
values. The test enables a finite private supported-class set; none of the
decorators exercised here is publicly admitted yet.

The public regression is `tests/test_provenance_feasibility.py`. It constructs two
mounts of the same subdag:

```text
literal token -> acquire Handle -> project dict -> number projection
                                                    |
                                                    v
                                      validation raw -> validator -> final gate
                                                    |
                                                    v
                                              mount output
```

`low` and `high` are declared parameterized-subdag mounts. `acquire` has a real
SDAX shutdown declaration. `number` comes from Hamilton `extract_fields`.
`resolve_from_config` invokes a counted callback that returns Hamilton
`check_output_custom`, producing raw, validator-evidence and final-gate nodes.

## Gate evidence

- The captured and unwrapped Hamilton graphs have identical generated names,
  output types and dependency mappings. The captured SDAX execution and a fresh
  stock Hamilton Driver both return `{"low": 2, "high": 5}`.
- The delayed callback and copied resolver run once for each actual mount. The
  recorded count is one for `low` and one for `high` in each construction context.
  Preparing or executing the lowered SDAX plan does not resolve them again.
- Capture records `low.acquire` as the acquisition, `low.number` as a projection,
  and the three `low.checked*` nodes as raw, validator evidence and final gate.
  The value feeding the projection remains the ordinary `VALUE` role because no
  persistent consumer needs a separate projection-source label. The test asserts
  the same complete role set for `high`. Dependency traversal from the low gate reaches exactly
  `low.acquire`; the high mount reaches exactly `high.acquire`.
- Borrowing is computed once from the compiler's final resolved-node mapping. A
  separate regression proves that a projection in one top-level declaration
  retains an owner from another declaration without building a second graph.
- A two-level mount regression uses different declarations with the same inner
  `low`/`high` namespaces under different parents. Roles and owners cross each
  namespace boundary through mount-scoped callable identity handoffs; no global
  generated-name table is used.
- Successful execution acquires and releases each mounted Handle once. When the
  low validation gate fails, both mounted acquisitions are still released once.
  The failure contains Hamilton's actual `DataValidationError`. Validation does
  not replay either acquisition.
- The original `acquire() -> Handle` and `checked(number: int) -> int` contracts
  remain available and unchanged. The fixture copies only function/decorator
  declaration containers; globals, closures, validators and other application
  objects retain identity.
- The original decorator instances, Hamilton's `base.resolve_nodes` function and
  a Driver constructed before the probe remain unchanged and usable afterward.
- The construction capture is observed through a weak reference and is collected
  after compilation even while the returned `NodeSpec` callables remain usable.
- Both a delayed resolver failure and a public `config` predicate failure preserve
  the original exception object, callback count, context and cause. Hamilton emits
  no error record, while an application log emitted immediately before the failure
  remains visible. After the caller drops the exception, the capture is collected.

## Proven local seam

The compiler uses four narrow interception points on copied declarations and copied
modifier instances:

1. Recursively clone the finite `parameterized_subdag.load_from` declarations
   with identity memoization. Copy the modifier containers while retaining
   application object identity.
2. Wrap the copied parameterized-subdag instance's generator creation. Each
   generated `subdag` instance establishes an explicit mount context from its
   declared namespace. Wrap its `add_namespace` operation so the exact pre- and
   post-namespace node objects are correlated while Hamilton performs the real
   namespace operation once.
3. Wrap `extract_fields.transform_node` and the returned validation modifier's
   `transform_node`. Delegate once, then classify the exact objects returned by
   those pinned family contracts. The fixture does not parse their names.
4. Wrap the copied delayed resolver's `resolve`. Delegate once, record the mount
   and exact returned modifier class, then wrap that returned instance for its
   normal Hamilton lifecycle step.

The compiler consumes temporary object-identity records during lowering. A
`finally` block detaches all instance methods and clears every capture table on
both success and construction failure. The local Hamilton node collection then
falls out of scope before the Driver becomes executable. The weak-reference check
proves that returned runtime callables do not retain the capture object.
Copied lifecycle methods carry ordinary callback failures through Hamilton as a
private `BaseException` transport and restore the original exception outside the
upstream logging boundary. `KeyboardInterrupt`, `SystemExit`, cancellation and
other user `BaseException` values are not caught.

No Hamilton compiler algorithm is copied. The complete set of version-coupled
object and ordering assumptions in this proof is:

- lifecycle decorators remain attached through their `get_lifecycle_name()`
  attributes, remain in Hamilton's lifecycle-list order and accept shallow copied
  instances with instance-bound method overrides;
- `parameterized_subdag.load_from` contains the declarations it recursively
  resolves, `_gather_subdag_generators()` returns actual `subdag` instances, and
  each instance exposes its declared namespace; generator creation precedes its
  one `generate_nodes()` call for the corresponding mount;
- `subdag.generate_nodes()` resolves `add_namespace` from that generated instance;
  `add_namespace()` returns one namespaced copy per input node in the same order;
- nested `resolve_nodes()` and its delayed modifier lifecycle complete while the
  generated subdag's explicit mount context is active;
- `Node.copy_with()` and recursive collection preserve the generated callable and
  `originating_functions` identities needed before namespacing;
- generated callable identity is stable only within one lifecycle expansion;
  pending lookup therefore includes an explicit mount token, retains a strong
  callable reference against `id()` reuse and consumes facts before disposal;
- the final namespaced node may be a copy rather than the exact object returned by
  a modifier; correlation therefore occurs at `subdag.add_namespace()`, before
  the copied node replaces its source;
- `extract_fields.transform_node()` returns its projection source first and its
  field projections afterward;
- `BaseDataValidationDecorator.transform_node()` returns validator nodes followed
  by the final gate and raw node;
- an untransformed standard node retains the copied declaration in
  `originating_functions`, allowing the actual call to be attributed before a
  generated family changes its callable;
- the delayed resolver is called from `get_node_decorators()` once per nested
  `resolve_nodes()` operation and returns the modifier instance used by that same
  lifecycle pass; and
- namespaced generated names are unique in the final collection, and final
  Hamilton `input_types` describe the dependency mapping consumed by the existing
  lowering and owner-reachability check.

These touchpoints must remain inside the existing private, fail-closed 1.90.0
compatibility boundary. A Hamilton upgrade must rerun this fixture and review each
item. Hamilton exposes no public callback carrying all four facts. Post-expansion
inspection loses facts, a global `resolve_nodes` patch affects unrelated Drivers,
and copying `resolve_nodes` would create the compiler replay this gate prohibits.

## Facts final nodes cannot establish

Hamilton gives the validation raw node, validator node and final gate the same
`originating_functions` ancestry in this fixture. Ancestry therefore cannot
distinguish their roles. Generated spelling happens to contain `_raw` and the
validator name, but that is a name convention rather than ownership evidence.

Final nodes also do not record which delayed resolver instance ran, how many times
it ran, which mount/configuration caused a resolution, or the exact modifier it
returned. They do not contain the SDAX shutdown-to-owner declaration relationship.
Once an acquisition is identified, final edges can prove that a projection or gate
depends on it; the edges alone cannot decide which ancestor is the real acquisition
and which generated values borrow from it.

## Implemented compiler delta

P2 now has a memoized recursive function-copy routine, a construction-local mount
context and exact-family wrappers for this bounded slice. The version-bounded
namespace hook correlates nodes before Hamilton replaces them while mounting. The
temporary records populate the existing `NodeSpec` mapping with only persistent
facts consumed by later work: generated role, original declaration and known
owner/borrow node. Mount identity stays temporary. The compiler retains no Hamilton
`FunctionGraph`, adds no second executable graph and exposes no modifier API.

P4 remains responsible for using those facts in selection and lifetime behavior.
The feasibility lowering attaches shutdown only to the two real acquisition nodes;
it is evidence for that rule, not the production implementation of recursive
ownership.

## Evidence still required

This gate does not complete broad P2, P3, P4, D0, D1, D2 or E. Integration still
needs per-family qualification and public admission, nested/shared mount cases,
selection/config/override protection, validation diagnostics policy, metadata
snapshots, broader decorator families and the full lifecycle composition suite.
The fixture covers one level and two mounts of one declared composition.
Before validation is publicly activated, shutdown's public declaration target must
be remapped to the captured actual raw call. The bounded fixture proves the default
`@shutdown(of=resource)` case, where the raw call is the sole actual candidate; it
does not yet qualify an explicit `target_="resource"` spelling when Hamilton has
renamed that call to `resource_raw`.
Packaging and Python 3.11/3.13 gates also remain outside this local feasibility run.

Local verification:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <qualification-python> -m pytest \
  -p no:cacheprovider tests/test_provenance_feasibility.py -q
6 passed in 0.57s

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <qualification-ruff> \
  check tests/test_provenance_feasibility.py
All checks passed!
```

The complete merged local source suite also passes: `252 passed in 3.46s`.
