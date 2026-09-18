# Hamilton 1.90.0 corrections — independent architecture review A6b

Date: 18 September 2026. Scope: U1 async output-pipeline correction and U2
generated loader annotation correction.

Reviewed integrated checkpoint:
`a154bf453f2b33ca68e77760987cf7500468ce13`.

Frozen correction artifacts:

- U1 helper `7503693b0a29666b8ed82369c0566f6038d9a8797f1940abd7ffc7c177b9980e`
- U1 tests `08ad0ff43f165fd9fcc4e284f6a213eed562a01e4367966168080bbc21dc749f`
- U1 report `cbe6c3bd4b791b0308d7b07d76d0000dd8888338d7a086a650590a23e8dd82d7`
- U2 helper `7aef562344b8b05eb2d2d2007f79402b013f5a096251b4605c55cc762a87a286`
- U2 tests `318ef942efe1c1e2be2405e427365d5cf4e653524bbc4269b77599b1af445e20`
- U2 report `411ea7626256e82ca5887ec6551175e6d8a282d91362f8097b0d909a4ffcbb1f`

## Verdict

**Pass U1 and U2 as private, pinned correction helpers.** Both demonstrate the
smallest credible correction for the inspected Hamilton 1.90.0 defect without
copying an upstream expansion algorithm, patching installed/global Hamilton state,
executing effects during compilation or admitting the surrounding decorator
family. C and F remain responsible for exact family admission and composition.

One medium code-minimization finding applies when U1 is wired into C: consolidate
its duplicate version check with the existing compatibility boundary. U2 already
uses the preferred caller-precondition design. This does not invalidate either
correction proof or block the P2/P3 foundation.

## U1 assessment

Hamilton's pinned `pipe_output.transform_node` creates an unannotated async exit
identity when its declaration is async. The same callable awaits a synchronous
identity result. U1 does not reproduce the transform. It wraps the exact copied
`pipe_output` instance's bound `transform_node` method and delegates once to the
installed implementation with a synchronous expansion-context proxy.

Inspection of the pinned implementation confirms the proxy is used only for the
async/sync branch and the declaration name passed to namespace resolution. The
actual producer callable remains on the copied input node and stays asynchronous.
The proxy is not emitted or executed. Hamilton continues to build the raw node,
pipeline steps, edges, namespaces and exit node.

The wrapper is instance-local, exact-class, idempotent and applied only to an
already copied declaration. Tests preserve the original declaration/modifier,
reproduce the uncorrected failure, verify generated order/names/types/edges and
coroutine classification, execute mixed sync/async steps through Hamilton's
AsyncDriver, and retain exception identity and cancellation. A separate negative
test confirms the helper does not add pipeline decorators to frontend admission.

The correction also covers `mutate`'s underlying defect because pinned `mutate`
constructs or extends exact `pipe_output` instances. That fact does not qualify
`mutate`; C still needs its own construction, targeting and ownership cases.

## U2 assessment

Hamilton's pinned `LoadFromDecorator.get_loader_nodes` emits a raw callable that
returns `(data, metadata)` while declaring the raw node as
`tuple[dict[str, Any], data_type]`. Its projection selects element zero. U2 copies
only the affected raw and projection nodes, corrects the raw annotation to
`tuple[data_type, dict[str, Any]]`, and changes the projection's corresponding
input contract to the same type.

The helper does not reconstruct loader selection, adapter construction, dependency
binding or the projection callable. It performs no registry lookup, loader call or
I/O. Tests verify no loader call occurs during correction, then execute the real
generated callable and projection. Correct data passes the raw and projected
checks; invalid data and reversed tuple order remain rejected. The original nodes
stay unchanged and repeated correction is identity-preserving.

Correction provenance is not inferred from names or tags alone. The private caller
must first establish an exact admitted `LoadFromDecorator` invocation and pass only
that invocation's isolated generated collection with `load_from_admitted=True`.
Within that boundary, the helper requires the complete pinned raw/projection tag
shape, common loader identity and an actual projection edge keyed by the raw node's
full name. Unadmitted tagged nodes return unchanged, including real `dataloader`
output. An admitted unexpected or ambiguous shape fails closed.

This two-part condition is important: the boolean is trusted compiler provenance,
not invocation data and not a value derived from node tags. F must compute it from
exact modifier admission before expansion and must not expose it through a public
API. If F merges unrelated nodes before calling the helper, the current provenance
argument no longer holds.

## Finding

### M1 — Medium at C integration: use one Hamilton version authority

U1 contains its own distribution/imported-source check and `1.90.0` constant even
though `hamilton_compat._check_version()` already performs that check before any
frontend compilation. U2 deliberately relies on the enclosing check and tests the
caller precondition. Once C invokes U1 immediately after declaration copying in
the same compile operation, the second check adds no safety but creates another
version constant, metadata lookup and upgrade edit.

Keep one fail-closed version gate in `hamilton_compat`. At integration, call U1 only
after that gate and remove its local checker/constant plus their duplicate tests,
replacing them with one call-site/precondition regression like U2. If the helper
must remain callable outside compilation for a concrete future consumer, retain
the local check and document that consumer; no such consumer exists now.

This consolidation should happen when C wires the helper, not by broadening U1 or
U2 into a correction registry. Both helpers are small and family-specific; a new
shim framework would cost more than the duplicated lines it removes.

## Boundaries

U1 does not qualify `pipe_output`, `pipe`, `pipe_input` or `mutate`. U2 does not
qualify `load_from`, `dataloader`, `datasaver`, registry precedence or I/O effects.
Neither helper changes SDAX scheduling, type-check ordering, retries, cleanup,
selection or public APIs. C and F must retain exact-class admission and add their
family-specific ownership, validation and unsafe-neighbor evidence.

The combined correction tests passed at the integrated checkpoint with bytecode
and pytest caches disabled (`16 passed in 0.73s`). The complete integrated source
suite passed under the same conditions (`208 passed in 2.49s`).
