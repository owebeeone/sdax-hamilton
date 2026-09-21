# Hamilton U1/U2 corrections: independent safety review A6a

Date: 18 September 2026. Reviewed integration commit:
`a154bf453f2b33ca68e77760987cf7500468ce13`. Scope: the private U1 async
output-pipeline and U2 generated-loader annotation helpers as correction
foundations. This review does not admit pipeline, mutate, loader, saver, adapter,
cache, or remote-execution families.

## Verdict

**PASS as bounded correction foundations. No blocking safety finding.**

Both helpers correct a reproduced Hamilton 1.90.0 defect without changing the
installed dependency, adding a global patch, executing graph effects during
inspection, weakening value checks, or granting runtime authority to metadata.
They remain private and inactive in the product compiler until their owning
family lanes separately admit exact forms and satisfy ownership, validation,
selection, and effect gates.

## U1: async output pipeline

The U1 helper operates only on an isolated function copy. It recognizes exact
`pipe_output` modifier instances and replaces only the copied instance's bound
`transform_node` method. It leaves original application declarations, Hamilton
classes, and process-global resolution functions unchanged.

The correction delegates once to Hamilton's installed transformation. Its
synchronous proxy supplies only the name and sync/async context used by the
pinned transformer. The proxy is not emitted as a node or executed. The original
coroutine remains on the raw producer node, while the generated identity becomes
synchronous and therefore does not await a non-awaitable pipeline result.

The regression witnesses the original missing-return-annotation failure, then
checks generated names, namespace, dependency chain, types, coroutine shape, and
the final value across synchronous and asynchronous steps. The call log shows no
producer or step effect during graph construction and exactly one of each during
execution. Separate cases preserve the original step exception object and caller
cancellation.

Applying the helper twice is idempotent. The original modifier's state remains
unchanged and continues to reproduce the upstream failure, while the copied
modifier resolves successfully. The helper checks both installed-distribution
and imported-source versions before mutation and fails closed unless both are
exactly Hamilton 1.90.0.

U1 does not add `pipe_output`, `pipe`, `pipe_input`, or `mutate` to compiler
admission. The current public Driver still rejects `pipe_output`. Phase C must
qualify exact forms, captured step arguments, ownership and validation behavior
before invoking this helper in production lowering.

## U2: generated loader tuple annotation

The U2 helper corrects the generated raw loader type from Hamilton's reversed
`tuple[dict[str, Any], data_type]` to the callable's actual
`tuple[data_type, dict[str, Any]]`. It updates the matching projection's input
contract to the same type. It does not reorder values, suppress the raw check, or
weaken the projected-value check. The invalid-value regression demonstrates that
both checks remain necessary and effective.

Correction requires an explicit `load_from_admitted=True` decision from the
future compiler call site. Complete loader tags identify candidate raw and
projection nodes only after that admission decision. The helper also requires a
shared loader identity and the actual raw-to-projection dependency. Tags alone
return unchanged nodes, and similarly tagged `dataloader` output does not
activate the correction. An admitted but unexpected or ambiguous shape fails
closed.

The helper copies corrected nodes and input mappings. Mutating the original
generated tags or input contract afterward does not change the corrected pair.
It is idempotent when Hamilton already supplies the expected annotation.

The counted in-memory loader is not called while nodes are generated or
corrected. It runs only when the corrected raw callable is explicitly invoked.
The helper performs no adapter lookup, adapter construction, registry inspection,
registry mutation, loader call, or I/O.

Unlike U1, U2 deliberately relies on the enclosing compiler compatibility gate
rather than duplicating version lookup. This is safe in the current integration
because no product call site invokes the helper and `load_from` remains rejected.
Before Phase F activates it, the call must remain after
`hamilton_compat._check_version()` and inside an exact per-function
`LoadFromDecorator` admission branch. The integrated family test must exercise
that call site under both distribution and imported-source mismatch. Direct use
of this private helper is not a supported cross-version API.

## Trust and authority boundaries

Decorator declarations, pipeline steps, adapter classes, registrations, and
compiler configuration remain trusted application code. These helpers do not
claim to sandbox them or undo import/decorator-time effects.

U2 reads known Hamilton tags only as structural evidence after an independent
admission decision. Those tags do not select an adapter, activate persistence,
or authorize execution. U1 reads copied modifier state but adds no runtime
backend or scheduler path. Both corrections leave SDAX execution and public APIs
unchanged.

Future C/F work still owns exact class admission, adapter identity snapshots,
registry precedence, construction-state rules, resource ownership, validation
composition, diagnostics, and runtime effect counts. U1/U2 passing does not make
those families supported.

## Frozen evidence

Reviewed SHA256 values:

- `_hamilton_pipeline.py`:
  `7503693b0a29666b8ed82369c0566f6038d9a8797f1940abd7ffc7c177b9980e`
- `test_pipeline_correction.py`:
  `08ad0ff43f165fd9fcc4e284f6a213eed562a01e4367966168080bbc21dc749f`
- `Pipeline-Correction.md`:
  `cbe6c3bd4b791b0308d7b07d76d0000dd8888338d7a086a650590a23e8dd82d7`
- `_hamilton_loader.py`:
  `7aef562344b8b05eb2d2d2007f79402b013f5a096251b4605c55cc762a87a286`
- `test_loader_correction.py`:
  `318ef942efe1c1e2be2405e427365d5cf4e653524bbc4269b77599b1af445e20`
- `Loader-Correction.md`:
  `411ea7626256e82ca5887ec6551175e6d8a282d91362f8097b0d909a4ffcbb1f`

Verification in the external qualification environment:

```text
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider \
  tests/test_pipeline_correction.py tests/test_loader_correction.py -q
16 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m pytest -p no:cacheprovider -q
208 passed

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  /Users/owebeeone/limbo/evidence-build-cache/hamilton-coverage-integrator/bin/python \
  -m ruff check --no-cache src tests
All checks passed!
```

No other reviewer findings were consulted. I changed no product, test, or
correction-report file.
