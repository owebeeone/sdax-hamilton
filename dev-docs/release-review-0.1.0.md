# v0.1.0 implementation release review

Reviewed the implementation after alpha commit `83e3024`, focusing on the public
contract for cancellation, partial acquisition, reverse cleanup and failure
preservation. This is an implementation review, separate from the earlier A6
design review. A separate reviewer checked compiler/type binding correctness.
The fixes below remain within the documented declaration subset
and require no SDAX core changes.

## Lifecycle findings and disposition

### R1: simultaneous caller cancellation and forward failure lost cancellation

**Release blocker; fixed.** On Python 3.11 and 3.12, SDAX's forward TaskGroup could
report a child failure while consuming concurrent cancellation of its parent.
The frontend then raised only an execution exception group, contrary to its
promise that caller cancellation remains primary after cleanup.

Minimal trigger: a forward callback calls `caller.cancel("external cancellation")`
on the task awaiting `plan.execute()` and immediately raises `ValueError`.
Before the fix, Python 3.11.14 and 3.12.12 raised an `ExceptionGroup` while
`caller.cancelling()` remained 1. Python 3.13.12 propagated `CancelledError`, but
lost the cancellation message. Cleanup ran in all three cases.

The frontend now retains a single task running SDAX's forward phase and shields
the caller's join. Caller cancellation is delivered directly to the caller; it
cancels the forward task once and then joins the draining phase despite further
caller cancellation. SDAX still owns node scheduling, retry and dependency
ordering. The caller's scope body continues to run in the caller's original task.
Only after forward work drains can shutdown start.

Regression coverage:

- `test_simultaneous_forward_failure_preserves_caller_cancellation`: cancellation
  message survives; the original forward error remains a secondary diagnostic.
- `test_repeated_caller_cancellation_joins_forward_drain_before_release`: a second
  cancellation cannot interrupt callback draining or release its resource early.
- `test_preexisting_cancellation_count_does_not_cancel_new_invocation`: previously
  handled cancellation does not spuriously cancel a later invocation or have its
  cancellation count consumed.

### R2: cleanup failure erased spontaneous forward cancellation

**Release blocker; fixed.** If a forward callback raised its own `CancelledError`
and shutdown subsequently raised `RuntimeError`, the final exception group
contained only the cleanup failure. The frontend decided whether to retain the
forward cancellation by checking core failures *after* shutdown, conflating
forward failures with later cleanup failures.

The frontend now snapshots forward failures before shutdown. A cleanup failure
cannot retrospectively erase the cancellation that terminated forward work.
Cancellation of siblings already explained by another forward failure remains
filtered, as before.

`test_forward_self_cancellation_survives_cleanup_failure` asserts that the final
aggregate contains both original exception objects.

## Type binding finding and disposition

### R3: nonempty tuples admitted to an empty-tuple consumer

**Release blocker; fixed.** `tuple[()]` and bare `typing.Tuple` both expose no
type arguments. Edge compatibility treated both as unconstrained, even though
runtime validation correctly requires an empty value for `tuple[()]`.

A real graph with `source() -> tuple[int]` returning `(1,)` and
`result(source: tuple[()]) -> int` incorrectly ran the consumer. The compiler now
distinguishes empty-tuple annotations from unconstrained tuples and rejects that
edge before any callback runs. Sixteen regressions cover both spellings of the
empty-tuple type, positive and negative assignability, and real graph rejection.

The compiler/type review also checked merged source contracts, config/override
pruning, optional inputs/defaults, ownership target coverage, shutdown signatures,
generated-node types, snapshot handling and runtime checks. No other concrete
blocker was identified within the admitted subset. Focused compiler/type tests
passed (120 cases), with clean lint and package/authoring type checks.

## Verified lifecycle boundaries

The focused lifecycle, retry and policy suite passes **55 tests** against the
changed source on Python **3.11.14, 3.12.12 and 3.13.12**. Ruff passes for the
changed implementation and test files; mypy passes for `plan.py`.

Existing coverage also verifies invalid returned resources remain available for
shutdown, an actual `None` differs from no acquisition result, independent cleanup
failures are retained, dependent resources release before their prerequisites,
cleanup retries finish before parent release, and repeated caller cancellation
does not abandon shutdown.

The documented partial-acquisition boundary is deliberate: an object allocated
inside a callback and lost before that callback returns cannot be recovered from
an `Acquisition` record. Such callbacks must clean up partial work internally or
split acquisition from fallible initialization. This review found no reason to
add a mid-acquisition publication protocol for this release.

Timeouts remain cooperative. A callback that blocks the event loop or refuses to
finish cancellation can prevent draining. Ordinary result aliases and
user-created background tasks remain the author's responsibility, as documented.

With R1 and R2 fixed and their cross-version regressions passing, no lifecycle
blocker remains within the documented v0.1.0 contract. This conclusion does not
replace the release's clean-artifact and publishing checks.
