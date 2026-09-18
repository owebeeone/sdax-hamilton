# Hamilton compiler foundation: independent safety review A6a

Date: 18 September 2026. Reviewed foundations:

- P2 culmination `24f7787` (`Capture Hamilton generated-node provenance`),
  including the production lowering introduced by its parent work;
- P3 `76a5d5603051e7eaf369126b9d43e1b60ffb4cba`
  (`Preserve original binding requirements`); and
- construction transport `654f39c19c1fecb7fb0f22e627eb28c21dc7dad9`
  (`Preserve construction failures outside Hamilton logging`).

This is a bounded review of the shared compiler foundation. It does not qualify
P4 ownership selection, recursive or delayed-resolution decorators, validation,
extraction, pipelines, I/O, plugins, caching, remote execution, or release.

## Verdict

**PASS for integration and for proceeding to P4 and family qualification. No
blocking finding remains in the reviewed foundation.**

P2 now lowers demonstrated generated-node provenance into the existing immutable
`NodeSpec` representation, disposes construction-only state, and retains one
authoritative dependency mapping. P3 preserves finite original consumer
requirements through selection and invocation without introducing another type
system. The construction transport prevents Hamilton's internal exception logger
from disclosing ordinary trusted-callback failures while returning the original
exception object to the caller.

This verdict does not activate any family that remains outside the public exact
class allowlist. The new role, borrowing and requirement fields are facts for
later gates; their presence alone does not provide the P4, D0/D2 or E behavior
described below.

## Construction failure boundary and reopened QA finding

The initial Phase A review accepted custom config predicates as trusted
construction code and proved that they run once. A later source inspection found
that Hamilton 1.90.0 wraps `base.resolve_nodes()` in `except Exception` and calls
`logger.exception()`. A predicate, model constructor or resolver exception could
therefore place its original message and traceback in automatic library logs.
This reopened the Phase A logging disposition: exact exception identity and a
single callback were insufficient while a synthetic secret could still reach the
default Hamilton logger.

The final correction uses a private `_ConstructionFailure` derived directly from
`BaseException`. Copied lifecycle methods catch ordinary `Exception` values and
raise that transport from no cause. Hamilton's `except Exception` does not catch
or log it. The sole outer construction boundary unwraps the stored exception
outside the transport handler and raises the original object with its original
traceback. Nested wrappers propagate an existing transport unchanged. User
`KeyboardInterrupt`, `SystemExit`, `asyncio.CancelledError` and other
`BaseException` values pass through directly.

The helper tests prove exact original identity, one callback, no transport in the
formatted exception, no context or cause, zero Hamilton-base log records, and no
mutation of the Hamilton logger's level, propagation or handlers. They also prove
the three named `BaseException` cases and a nested wrapper path.

P2 wires this helper into every copied modifier lifecycle and replaces its only
production `base.resolve_nodes()` call with the private boundary. A public
`Driver` regression now exercises the previously exposed custom-config path. It
proves original identity, one callback, no context or cause, zero Hamilton-base
records, preservation of an unrelated application log, and collection of the
temporary capture after the caller drops the exception. This closes the bounded
A/QA logging gap. Broader callback-bearing families remain disabled and require
their own construction-error cases before activation.

## P2 provenance and lifetime facts

The compiler recursively clones the finite demonstrated declaration closure with
memoized function identity. Modifier instances and the binding containers that
the compiler or Hamilton may alter are copied. The final corrections also copy
`parameterized_subdag.external_inputs` and copy a modifier returned from the
shared delayed resolver before installing capture methods. Globals, closures,
validators and identity-sensitive application payloads remain trusted
application state, as required by the plan's bounded snapshot policy.

Projection and validation wrappers record role, original declaration and whether
the generated node performs the declaration's actual call. Mount correlation is
based on callable identity plus an explicit mount token. At each namespace
boundary, the fact is handed to the parent mount using the copied callable; no
global generated-name inference is used. Strong callable references prevent
`id()` reuse while construction is active.

An early review candidate lost an inner fact at a second namespace boundary. A
two-level reproduction turned `top.low.number` from a projection into an ordinary
value, erased its borrow edge and could make it a false shutdown candidate. The
final parent-mount handoff fixes this. Its maintained adversarial regression uses
different outer declarations with the same inner `low`/`high` namespaces and
proves distinct origins, preserved projection roles, correct owners and no false
projection ownership.

Borrow discovery originally needed scrutiny across top-level declaration roots.
The final implementation computes borrowing after all resolved nodes and facts
have entered the compiler's final mapping. A maintained regression selects a
projection declared separately from its acquisition and proves that the
projection borrows the owner and that execution acquires and releases once.
Within the compositional fixture, both mounts retain independent acquisition,
projection, raw-validation and validation-gate facts. Construction resolves each
delayed callback once per actual mount and execution does not replay it.

Shutdown attachment uses captured original declaration identity and the
`actual_call` fact. The bounded fixture attaches cleanup only to each real mounted
acquisition. Successful execution and validation failure both release each mount
once. Projections, validation raw values and gates retain the known owner in
`borrow_from`; validator evidence is deliberately not presented as an ownership
alias.

The capture is finalized in a `finally` block on success and construction
failure. Installed instance methods are detached and identity tables are cleared.
Weak-reference regressions prove collection after successful public compilation
and after a failing delayed resolver, while the lowered runtime callables remain
usable in the success case. Original decorator instances, annotations, Hamilton's
global resolver and a previously built Driver remain unchanged.

## P3 binding contract

`InputSpec.requirements` is an immutable tuple of original consumer requirements.
An empty tuple falls back to the declared effective input type. Multiple entries
form a finite conjunction evaluated with the existing `_types` vocabulary; this
does not infer intersection types or create another graph or checker.

Selection validates every effective requirement for producer edges, defaults,
configuration inputs and configuration replacements. Invocation validates the
complete external-input and override shapes before scheduling callbacks, then
checks every supplied value against all relevant consumer requirements. A
generated value is checked again at the consumer-call boundary before that
consumer runs, including when `check_outputs=False`; that flag continues to
control only the producer's declared output check.

The regression matrix covers compatible and unsafe edges, invalid defaults,
configuration and overrides, conjunctive external and override requirements, and
the disabled-output-check path. Invalid external or override data is rejected
before independent effects. When an owned producer returns a raw value that fails
the consumer requirement, the consumer does not run and the already acquired raw
value is released exactly once.

The current compiler deliberately emits no additional original requirements.
Phase B owns capture for merged Hamilton bindings. Until B qualifies that capture,
the declared type remains the fallback and the existing fail-closed binding
rejections remain in force.

## Independent recursive failure probe

In addition to the maintained suite, I ran a read-only concrete probe through two
real Hamilton `resolve_nodes` boundaries: an outer `parameterized_subdag` mounted
an inner `resolve_from_config` whose trusted callback raised a pre-created
sentinel. The result was the exact sentinel object, one callback, no context or
cause, and zero records from `hamilton.function_modifiers.base`. This confirms
that the copied inner lifecycle transports the failure before Hamilton's inner
logger can observe it.

That probe is independent review evidence, not a maintained repository test. The
existing maintained nested-wrapper test is synthetic, and the maintained
two-level mount test exercises successful resolution. D0/D2 activation must add
a real recursive-failure regression that preserves this no-log and single-call
behavior.

## Retained activation gates

- P4 still owns selection and lifetime use of `role` and `borrow_from`: selected
  aliases must retain owners, replacement and escape must remain blocked, and
  validation evidence must not bypass the mandatory gate.
- E must remap an explicit public shutdown or policy target from the declaration
  name to the captured actual raw-validation call. The bounded default
  `@shutdown(of=resource)` case is safe because the raw call is the sole actual
  candidate. An explicit `target_="resource"` does not yet name Hamilton's
  generated `resource_raw` node and therefore remains an activation blocker.
- D0/D2 must qualify recursive discovery, hidden admission and real nested
  construction failure as maintained public behavior. The private `_supported`
  test entry is evidence scaffolding, not public admission.
- E still owns validation diagnostics, mandatory fail gates under
  `check_outputs=False`, and family-specific raw/gate targeting. P3's synthetic
  raw release case does not qualify Hamilton validation.
- B must populate distinct original binding requirements. F must retain selected
  adapter identity. No reviewed field authorizes imports, I/O, persistence,
  caching or remote execution.

## Frozen evidence and verification

P2 frozen SHA256 values:

- `tests/test_provenance_feasibility.py`:
  `fe3b1191f32ab04c98ecf88ef593f7492c302d9a720db05c099c8c1051ff76ac`
- `dev-docs/Provenance-Feasibility.md`:
  `8ded11c04e8081ab21001e7375c73f17e94893f1f6c49028848ee32f02a50402`
- `src/sdax_hamilton/hamilton_compat.py`:
  `2daf0261de87971075930042a6ea3dc124ce0115e060805cb7d1be9caa8862ef`
- integrated `src/sdax_hamilton/_model.py`:
  `e64fc13f955618b6dc5a92742420ea490a176505ba6fc51657c55380c89132bf`

Construction-transport commit hashes:

- `src/sdax_hamilton/_construction.py`:
  `ccdecea37d2fdc3b5c0833353233550b2d227215893b8068d05059cf0a29f5a5`
- `tests/test_construction_failures.py`:
  `f938c0393908826a573446f979909f6ca17aa45fe85ab488e5b04ab26f32a904`

P3 commit-file hashes:

- `src/sdax_hamilton/_model.py`:
  `e8c849672ddb697f56f4d0bdd54ec98592dc2b95e80f298839e90a98fdf70b0e`
- `src/sdax_hamilton/_runtime.py`:
  `ca632a5acedd45f39393c88332b3b8ce8da7b1a5eace9f317f5c3d55440fd8c2`
- `tests/test_binding_contracts.py`:
  `a647e5747decde8769358fbd2f2134825f828556fb22d7d8aacfbd912f195e2a`
- `dev-docs/Binding-Contracts.md`:
  `ebc337eb2febd35a85fa81d7e41897a661329fa1442fe285e88ae0a26593fbd2`

Independent verification used the external read-only qualification environment
with bytecode and pytest cache writes disabled:

```text
P2 provenance tests: 6 passed
P2 plus construction-transport tests: 11 passed
Merged source suite in the P2 lane: 252 passed
Ruff on the reviewed P2/construction files: All checks passed!

P3 binding-contract tests: 12 passed
Full source suite at the P3 review point: 202 passed
Ruff on the reviewed P3 source and tests: All checks passed!
```

No other reviewer findings were consulted. I changed no product or test file in
performing this review.
