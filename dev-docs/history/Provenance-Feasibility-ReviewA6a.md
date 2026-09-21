# Compositional provenance feasibility: independent safety review S

Date: 18 September 2026. Reviewer: independent safety lane. Scope: plan task S
only; this is a feasibility decision for starting P2/P3, not product
qualification or decorator activation.

Reviewed frozen artifacts:

- `tests/test_provenance_feasibility.py` SHA256
  `061eefab567cfa0023c5a57e4b4971ad981244ef46da3361c6eeaf28598a34a8`
- `dev-docs/Provenance-Feasibility.md` SHA256
  `f7010491a3f8cf121f0d1c2c1ac81a3133fd44e4bb3be1b00c49a3a869d835c1`
- Plan authority `dev-docs/Decorator-Support-Plan.md`, especially
  S/P2/P3/P4/D0/D2/E and the shared reuse/composition gates.

## Executive verdict

**GO for P2 and P3. No gate-blocking safety finding in the bounded S proof.**

The frozen test demonstrates a plausible, narrow interception seam through
Hamilton 1.90.0 without a global patch, compiler replay, retained executable
graph, or second scheduler. It identifies the actual acquisition and generated
projection/validation roles before namespacing, preserves two mount contexts,
lowers once to the existing `NodeSpec`/`PreparedPlan` execution path, and
witnesses exactly-once acquisition/release on both success and validation
failure.

This verdict authorizes foundation work only. It does not qualify recursive
decorator support, establish production ownership enforcement, admit validation
outputs for selection, or satisfy P4/E/D0/D2. The report states those limits
accurately.

## Evidence reviewed

The successful case directly witnesses:

- separate `low` and `high` resolver events, exactly once per mount path;
- exact generated roles for `low.acquire`, `low.number`, `low.checked_raw`,
  `low.checked_minimum`, and `low.checked`;
- dependency traversal from each final validation gate to exactly its own
  mounted acquisition (`low.acquire` or `high.acquire`);
- one acquisition and one release for each token, with captured and stock
  Hamilton values both equal to `{"low": 2, "high": 5}`;
- graph signature parity between the probed and stock Hamilton expansion;
- the original `base.resolve_nodes` object, original decorator attachment
  collection, and an already-prepared unrelated Driver remaining usable after
  capture.

The failure case sets a minimum that rejects the low mount while admitting the
high mount. It directly witnesses one resolver event per mount and exactly one
acquisition/release for both mounted resources after failure. A read-only
auxiliary inspection of the frozen case confirmed the exception group currently
contains Hamilton `DataValidationError`; the committed regression itself asserts
only `BaseExceptionGroup`.

The capture mechanism classifies exact returned node/callable objects. It does
not derive acquisition, projection, raw-validation, validator, or final-gate
roles from generated spelling. The assertion that the three validation nodes
have identical `originating_functions` ancestry is especially useful: it
demonstrates why final-node ancestry alone cannot recover those roles.

Verification against the frozen files:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider tests/test_provenance_feasibility.py -q
2 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m ruff check --no-cache tests/test_provenance_feasibility.py
All checks passed!
```

## Safety assessment

**Actual acquisition and borrowing.** `low.acquire` is classified from the
original declaration carrying the SDAX shutdown relationship, and shutdown is
attached only to acquisition-role nodes during lowering. `low.number` is
classified as a projection, while final-edge traversal reaches only the
corresponding mounted owner. This is sufficient evidence that P2 can carry a
generated role plus owner/borrow origin in the existing model. It is not yet
production ownership enforcement; P4 must make selected aliases retain owners
and reject replacement or escape.

**No duplicate effects and shutdown.** The delayed construction callback is
counted once per actual mount. The effectful acquisitions are counted once, and
shutdown is counted once per acquired Handle on both success and validation
failure. The source wrappers delegate each intercepted transform once. Pure
projection, checked-function, and validator execution are not separately
counted, so the later lifecycle composition suite should count those
user-visible calls as well; that is hardening for production qualification
rather than a blocker to the seam decision.

**Independent mounts.** The proof uses the same component declarations mounted
under two namespaces with distinct literal inputs. Recorded mount paths,
dependency traversal, and acquired Handle values all distinguish the mounts.
This is a real two-mount witness. It does not cover nested/shared/cyclic
declarations; the report correctly leaves those to D0 and later integration.

**Source and process-global mutation.** The probe operates on copied function
and modifier containers, patches the copied `parameterized_subdag` instance,
and leaves the process-global `resolve_nodes` function unchanged. The
pre-existing Driver check is a useful global-pollution sentinel. The test also
checks that the original parameterized-subdag modifier did not receive the
instance patch. It does not deeply snapshot every original modifier field,
function metadata container, global, closure, or validator identity. P2
therefore still needs declaration-metadata mutation and identity-sensitive
application-object regressions before claiming the plan's finite snapshot
boundary.

**Trusted code versus invocation data.** The delayed resolver callback and
custom validator are trusted construction/application code, consistent with the
plan's threat boundary. The fixture does not represent hostile Python and should
not be described as sandbox evidence. Its `parameterized_subdag` literals and
resolver configuration are declaration/control inputs, not untrusted runtime
values. No runtime value selects imports, registrations, decorators, or
execution profiles in this slice. Hostile metadata, diagnostic sentinels, and
mutation-after-build behavior are absent and remain required in P2/E/F and
release gates.

**Validation bypass.** S successfully captures raw, evidence, and final-gate
roles at the only point where they are distinguishable. It does not enforce that
raw/evidence nodes are internal, reject selection/config/override replacement,
prove `check_outputs=False` preserves Hamilton fail-validation, or include an
edge-removal negative control. Those are explicit P4/E responsibilities in the
plan and report, so their absence does not fail S. They must remain blocking for
activation even though P2/P3 may now start.

## Nonblocking witness limitations

1. The validation-failure regression should eventually assert the expected
   Hamilton validation leaf (or another stable semantic predicate), because
   `pytest.raises(BaseExceptionGroup)` would also accept an unrelated grouped
   failure. The frozen implementation currently fails for the intended validator
   reason; this is a regression-strength issue.
2. The regression asserts all principal low-mount roles but does not directly
   assert `PROJECTION_SOURCE` or full high-mount role parity. The two owner-path
   assertions and distinct lifecycle events establish the gate's central
   mount/ownership result, but P2's production tests should enumerate every
   consumed role for both mounts.
3. The success test checks resolver count before execution, whereas the failure
   test checks it after execution. The lowered execution path contains no resolver
   and the failure witness proves no execution-time resolution in that path; a
   final post-success count would make the no-replay claim more explicit.

## Required boundaries after this decision

P2 may implement only the demonstrated construction-local seam: memoized
recursive declaration copies, explicit mount context, exact-family wrappers
inside the pinned private compatibility boundary, temporary identity records
discarded after lowering, and the minimal role/origin/borrow/metadata fields with
named consumers. P3 may build on the preserved original consumer requirements
and representation cases using the existing bounded checker.

P4/E/D0/D2 remain responsible for recursive admission, selection and override
protection, validation-evidence bypass prevention, mandatory validation under
`check_outputs=False`, nested/shared mounts, diagnostics policy, and full counted
lifecycle composition. No decorator in this proof is admitted by the product
compiler merely because S passes.

No other reviewer findings were consulted. No product or evidence files were
changed.

## Final refinement disposition

The contributor subsequently refined the proof without changing its design or
scope. This disposition reviews the final frozen artifacts:

- `tests/test_provenance_feasibility.py` SHA256
  `4f52f311a455fd269039dd8957aef4e77ac83553644c04f52395dd74b34bc95b`
- `dev-docs/Provenance-Feasibility.md` SHA256
  `15d47acda1017655a13c1a6560766b80e27730417aee692412a2ab25dea6ab33`

The refinements resolve all three nonblocking witness limitations recorded
above. The failure regression now inspects grouped leaves and requires a
Hamilton `DataValidationError`. Both mounts now assert the complete acquisition,
projection-source, projection, raw-validation, validator, and final-gate role
map. The successful execution now rechecks the resolver count after execution,
making the no-replay witness explicit.

The report also names the exact pinned Hamilton ordering and identity properties
on which the probe depends, including generator namespace wrapping,
`Node.copy_with()` identity preservation, projection and validation result
ordering, delayed resolution, and final dependency mappings. These remain
properly confined to a fail-closed Hamilton 1.90.0 compatibility boundary.

The final frozen test passes its two focused cases and Ruff check in the stated
external qualification environment. The original verdict is unchanged:
**GO for P2 and P3, with P4/E/D0/D2 and release qualification still open.**
