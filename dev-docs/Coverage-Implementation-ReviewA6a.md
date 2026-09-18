# Hamilton coverage implementation safety review — A6a

## Disposition

The reviewed production snapshot was
`e0093b54147733cec5bd8fdef4bb03cd7f6e3163`. It initially failed this bounded
safety review because Hamilton I/O decorators could participate in the admitted
caller-owned Spark profile. The root correction present at the end of this
review closes that finding. I found no other concrete release-blocking defect in
the reviewed generated-provenance, ownership, validation, delayed/nested,
I/O-retry, cleanup, or Spark boundaries.

My final bounded disposition is **PASS after the targeted Spark/I/O correction**.
This disposition applies to the corrected source and its focused regressions; it
does not turn the explicitly documented compatibility restrictions into supported
behavior. The correction must be included in the release commit and artifact
checks. I did not authorize a push, publication, or release.

The supplied release evidence reports 434 installed-wheel tests passing on each
of Python 3.11, 3.12, and 3.13, with all five optional installed-wheel profiles
also passing. I treated those runs as supplied evidence and did not repeat broad
suites. I inspected the root checkout directly and ran only the five new Spark
construction regressions plus focused lint and diff checks.

## Initial P1 finding: Hamilton I/O escaped the Spark ownership boundary

At `e0093b5`, `_hamilton_spark.py:28-44` walked only ancestors of the exact
generated Spark nodes. It rejected SDAX ownership, release, borrowing, and
nondefault policies, but did not identify Hamilton loader/saver nodes. The guard
was invoked after lowering at `hamilton_compat.py:553-554`. This left two concrete
paths outside the claimed caller-owned, lazy-plan profile:

1. A `load_from` DataFrame node could feed `with_columns`. Driver construction
   accepted loader/select nodes as Spark ancestors. The adapter callback could
   therefore create a session or DataFrame even though this profile requires the
   Spark session and input DataFrame to be caller-owned.
2. A `save_to` sink could consume a Spark result directly or through an ordinary
   forwarding node. A saver is downstream of the Spark nodes, outside an
   ancestor-only walk. The sink also remained an explicit execution-policy target
   through `_hamilton_provenance.py:591-630`. A saver may call a synchronous Spark
   action such as `collect()`; that blocks the event loop and prevents SDAX from
   enforcing timely timeout/cancellation while it runs.

The first reproduction registered a `DataLoader` applicable to
`pyspark.sql.DataFrame`, then constructed this graph without executing it:

```python
@load_from.sdax_review_spark_source()
def frame(loaded: DataFrame) -> DataFrame:
    return loaded

@with_columns(
    primitive_double,
    columns_to_pass=["value"],
    select=["primitive_double"],
    namespace="enriched",
)
def enriched(frame: DataFrame) -> DataFrame:
    return frame
```

`Driver(module)` was accepted and contained `frame.load_data.loaded`,
`frame.select_data.loaded`, and the Spark nodes. The second reproduction put
`@execution(target_="sink", timeout=1)` and a registered DataFrame `@save_to`
outside the same `@with_columns` declaration. It was accepted with a `sink` node
whose input was the Spark result and whose timeout was one second. Neither
reproduction needed to invoke an adapter or start a Spark session, so these were
construction-policy failures rather than speculative runtime scenarios.

## Closure of the P1 finding

The targeted correction adds `reject_spark_io()` at
`_hamilton_spark.py:9-12`, using Hamilton's reserved
`hamilton.data_loader`/`hamilton.data_saver` tags. The completed-graph guard now:

- applies that check to the full ancestor cone before the existing ownership,
  release, borrowing, and policy checks (`_hamilton_spark.py:34-51`);
- walks descendants of the exact Spark nodes, including ordinary forwarding
  nodes, to reject downstream savers (`_hamilton_spark.py:53-68`); and
- leaves sibling I/O branches alone because descendant traversal starts at the
  exact captured Spark nodes rather than their shared ancestors.

Nested column functions require an earlier check: Hamilton combines their native
generated nodes before the final graph exists, and a later namespace operation
can obscure the originating wrapper. The correction checks those exact generated
nodes before native Spark UDF combination at
`_hamilton_provenance.py:1052-1061`. This uses the same reserved Hamilton tags and
does not execute or reinterpret the callback.

The maintained public regressions at `tests/test_spark_driver_profile.py:327-436`
cover a connected loader, a direct saver with an explicit timeout, an indirect
saver through a plain forwarding node, an unrelated I/O branch that remains
accepted, and a dataloader nested inside `with_columns`. Each rejection happens
during `Driver` construction with zero adapter-construction effects and no active
Spark context.

I reran those exact cases in the pinned Spark profile:

```text
5 passed, 8 deselected
```

Focused Ruff and `git diff --check` also passed. At the reviewed closure point,
the relevant working-tree SHA-256 values were:

- `_hamilton_spark.py`:
  `bef3373dd82a63e8d28a41bf4164116aecdccdb4afc1046f960498a009be62c6`
- `_hamilton_provenance.py`:
  `bc8a63d5ec796ece4480bc94006d2c2f97799821f693b65c2a09b4e89691b032`
- `tests/test_spark_driver_profile.py`:
  `4797b46fce16c34be46e516d575378db7ed0b962ab6da172894f92219b4c8fe7`

This correction is sufficient for the documented restricted profile. It does
not attempt to recognize arbitrary trusted Python that starts a Spark action,
which is neither statically enforceable nor part of this compiler's safety
model.

## Other reviewed safety boundaries

Generated facts remain construction-local and feed concrete lowering fields.
Exact callable identity and mount distinguish independent expansions; namespace
handoff verifies shape/order before transferring facts and input contracts.
Ownership is attached only to the actual acquisition call, while derived
projections borrow that owner. Selection rejects missing release callbacks,
replacement of owned or borrowed nodes, invalid owner references, and acquisition
retry. Runtime cleanup remains SDAX-owned and receives an empty `Acquisition` on
pre-call failure or the populated acquisition after success, so the qualified
success, failure, and cancellation paths release exactly once.

Validation raw/evidence nodes cannot be selected, and raw/evidence/gate or
borrowed nodes cannot be replaced by config or override. Internal validation
edges have an explicit role allowlist. The mandatory generated gate remains in
the selected graph when frontend return checking is disabled with
`check_outputs=False`; validation failure does not retry the upstream acquisition.
I found no alternate raw-output route around these checks.

Delayed modifiers resolve once, admit only the exact supported returned modifier,
and pass through the same snapshot, instrumentation, and final lowering. Only
the return annotation preflight is deferred for the qualified delayed validation
profiles; parameter/default checks still precede the resolver, and the generated
node type is validated before runtime callbacks. Recursive subdag construction
tracks each actual source declaration separately, rejecting direct and nested
self-cycles while permitting legitimate sibling reuse. Plain pipeline/`does`
helpers remain code-only helpers because Hamilton does not expand lifecycle
decorators attached to those helpers.

Hamilton I/O adapters are selected and snapshotted during construction, but their
instances are constructed inside the SDAX-timed attempt. Loader retries recreate
and reload the adapter per attempt. Saver retries recreate and save per attempt
without rerunning the producer. A loader's raw acquisition owns cleanup and its
public projection borrows it. A SaveTo sink returns fresh trusted metadata and
does not borrow the producer; the normal data dependency keeps the producer live
through the save. The metadata non-alias property remains an explicit trusted
adapter contract.

## Scope and retained limitations

This is a bounded review of the documented static decorator allowlist at the
pinned Hamilton 1.90.0 and SDAX 0.7.2 interfaces. Construction runs trusted
Python and is not a sandbox. Application defaults, closures, globals, validators,
models, and adapter state retain ordinary Python identity and trust semantics.

The Spark profile remains caller-owned, classic-local, and lazy. Standalone
`require_columns`, Spark decorators inside Hamilton subdags, owned inputs,
borrowed/released values, nondefault policy in the Spark chain, Hamilton I/O in
ancestors/descendants/nested UDF expansion, Spark Connect, and remote/background
work are unsupported. A synchronous action invoked by trusted Python blocks the
event loop, delaying timeout, cancellation, and cleanup until it returns. A lazy
result or externally launched job may outlive the SDAX call, so the caller must
retain the session and resources until the work is actually complete.

The full installed-wheel matrix is strong compatibility evidence, but it does
not prove arbitrary decorator compositions or application callback behavior.
The root's publish-matrix and installed-source import-boundary changes were
separate release hardening performed during this review; production assessment
here remains centered on the generated-provenance and execution-safety contracts
above.
