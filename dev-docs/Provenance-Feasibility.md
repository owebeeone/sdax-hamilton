# Compositional provenance feasibility

Date: 18 September 2026. Hamilton: 1.90.0. SDAX: 0.7.2. Plan task: S.

## Result

The feasibility gate passes for its bounded slice. A test-local compiler probe
captures mount, acquisition, projection and validation roles while delegating each
Hamilton lifecycle operation once. It does not replay `resolve_nodes`, infer roles
from generated names, patch process-global Hamilton objects, introduce a retained
product graph, or change SDAX core. The probe temporarily keeps its Hamilton nodes
and capture records so the test can inspect them. It lowers those nodes into the
existing `NodeSpec`/`PreparedPlan` path only to prove real acquisition and release
behavior. No decorator exercised here is admitted by the product compiler yet.

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
  recorded counts are `{("low",): 1, ("high",): 1}` in each construction context.
  Preparing or executing the lowered SDAX plan does not resolve them again.
- Capture records `low.acquire` as the acquisition, `low.number` as a projection,
  and the three `low.checked*` nodes as raw, validator evidence and final gate.
  It also records the projection-source role, and asserts the complete same role
  set for `high`. Dependency traversal from the low gate reaches exactly
  `low.acquire`; the high mount reaches exactly `high.acquire`.
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

## Proven local seam

The probe uses four narrow interception points on copied declarations and copied
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

The probe retains temporary object-identity records and its Hamilton node tuple so
assertions can inspect them after lowering. This proves that execution needs only
the lowered `NodeSpec` mapping; it does not itself prove production object lifetime.
P2 must consume the records during lowering and discard both the capture tables and
Hamilton node collection before a Driver becomes executable, as the current
compiler discards its temporary Hamilton graph.

No Hamilton compiler algorithm is copied. The complete set of version-coupled
object and ordering assumptions in this proof is:

- lifecycle decorators remain attached through their `get_lifecycle_name()`
  attributes and accept shallow copied instances;
- `parameterized_subdag.load_from` contains the declarations it recursively
  resolves, `_gather_subdag_generators()` returns actual `subdag` instances, and
  each instance exposes its declared namespace;
- `subdag.generate_nodes()` resolves `add_namespace` from that generated instance;
  `add_namespace()` returns one namespaced copy per input node in the same order;
- `Node.copy_with()` and recursive collection preserve the generated callable and
  `originating_functions` identities needed before namespacing;
- `extract_fields.transform_node()` returns its projection source first and its
  field projections afterward;
- `BaseDataValidationDecorator.transform_node()` returns validator nodes followed
  by the final gate and raw node;
- the delayed resolver is called from `get_node_decorators()` once per nested
  `resolve_nodes()` operation and returns the modifier instance used by that same
  lifecycle pass; and
- final Hamilton `input_types` describe the dependency mapping consumed by the
  existing lowering and owner-reachability check.

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

## Minimum follow-on compiler delta

P2 needs a memoized recursive form of the current function-copy routine, a
construction-local mount context and exact-family wrappers for the families it
actually admits. It also needs a version-bounded namespace correlation hook because
Hamilton replaces node objects while mounting. The resulting temporary records can
populate the existing `NodeSpec` mapping with only facts consumed by later work:
declaration/mount identity, generated role and known owner/borrow origin. P2 should
not retain a Hamilton `FunctionGraph`, add another executable graph, or expose this
probe as a public modifier API.

P4 remains responsible for using those facts in selection and lifetime behavior.
The feasibility lowering attaches shutdown only to the two real acquisition nodes;
it is evidence for that rule, not the production implementation of recursive
ownership.

## Evidence still required

This gate does not complete P2, P3, P4, D0, D1, D2 or E. Integration still needs
public product fields and consumers, recursive admission checks, nested/shared
mount cases, selection/config/override protection, validation diagnostics policy,
metadata snapshots, broader decorator families and the full lifecycle composition
suite. The fixture covers one level and two mounts of one declared composition.
Packaging and Python 3.11/3.13 gates also remain outside this local feasibility run.

Local verification:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <qualification-python> -m pytest \
  -p no:cacheprovider tests/test_provenance_feasibility.py -q
2 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src <qualification-ruff> \
  check tests/test_provenance_feasibility.py
All checks passed!
```
