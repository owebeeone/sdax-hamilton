# Hamilton 1.90.0 async output-pipeline correction

U1 corrects one pinned Hamilton defect without changing Hamilton's installed
source, patching a Hamilton class globally, adding a fork, or admitting pipeline
decorators to the SDAX frontend. The helper is private:
`sdax_hamilton._hamilton_pipeline.correct_copied_async_output_pipelines`.

## Defect and boundary

In Hamilton 1.90.0, `pipe_output.transform_node()` builds an unannotated async
identity for an async declaration. `Node.from_fn()` rejects that identity for its
missing return annotation. The same identity awaits its synchronous result, which
would fail after the annotation problem was removed. `mutate` constructs or
extends `pipe_output` instances, so it has the same underlying defect when C
qualifies it.

The correction receives a declaration already copied by
`hamilton_compat._copy_function`. For each exact copied `pipe_output` instance,
it replaces only that instance's `transform_node` method. The replacement delegates
to the installed implementation with a synchronous expansion-context proxy for an
async declaration. In the pinned source, that argument is used only to select the
artificial identity's sync/async shape and to read `__name__` for the artificial
step and namespace. The proxy preserves those names. It is never installed as a
Hamilton node or called during execution. The copied input node still retains the
original coroutine callable, so Hamilton's async execution continues to await the
actual producer.

The correction copies **zero lines of Hamilton's transformation algorithm**. It
does not alter an original declaration or modifier, and repeated application to a
copy is idempotent. The source-derived facts above are regression tested through
the generated names, namespace, edge inputs, types, coroutine classification,
values, exception identity, cancellation and original-declaration immutability.

## Integration contract

Phase C may call the helper immediately after `_copy_function` and before
`base.resolve_nodes`. It must retain the existing admission check: U1 does not
add `pipe_output`, `pipe`, `pipe_input`, or `mutate` to `_SUPPORTED`, and it does
not change SDAX execution, graph lowering, or public APIs. C must separately
qualify exact supported pipeline forms and their ownership/validation behavior.

The helper checks both the installed distribution and imported source version and
fails closed unless each is exactly `apache-hamilton==1.90.0`. Remove it when an
upstream Hamilton release fixes both the return annotation and synchronous
identity behavior, after the replacement version is re-inventoried and all U1
regressions pass against it. An upstream upgrade is not covered by this correction.
