# Implementation status

Date: 18 September 2026. Initial alpha: `0.1.0a1`.

The repository now contains a standalone alpha package. This file records current
product work; the earlier design, adversarial
review and comparison report remain historical records.

## Scope of this increment

- A narrow compiler using real Hamilton declarations over a separate typed
  binding/ownership representation.
- Existing SDAX execution and shutdown, reusable prepared processors and fresh
  per-invocation contexts; no SDAX core or Hamilton fork changes.
- Explicit policies, raw/validated acquisition records and cancellation/cleanup
  diagnostics.
- Maintained public tests, package metadata, API documentation and CI independent
  of private evidence and `scratch/`.

The current [API](../docs/API.md) and [compatibility limits](../docs/Compatibility.md)
supersede proposed spellings in the original design when they differ. In particular,
`Driver(*modules, config=None)` is the constructor, output checks default to enabled,
raw availability is distinct from valid typed access, and retry defaults follow
the pinned SDAX version with a one-second initial delay.

## Validation

The maintained suite contains **155 tests**, including early rejection cases.
Both direct dependencies were installed from their published PyPI distributions,
not workspace source overlays: `sdax==0.7.2`, `apache-hamilton==1.90.0`.

| Check | Executed result |
|---|---|
| Source checkout, Python 3.12.12 | 155 tests passed. |
| Built wheel, clean Python 3.11.14 environment | 155 tests passed. |
| Built wheel, clean Python 3.12.12 environment | 155 tests passed. |
| Built wheel, clean Python 3.13.12 environment | 155 tests passed. |
| Standalone lifecycle example | Passed in all three wheel environments. |
| Ruff, source/tests/examples | Passed. |
| Mypy, package and authoring contract | Passed; installed-package authoring contract also passed in each wheel environment. |
| Source distribution and wheel | Built successfully; wheel built from source distribution. Public tests included in source distribution; typing marker included in wheel; scratch/private evidence/caches excluded. |

All runs above were local on macOS/Apple Silicon. Clean-wheel tests used copied
public tests outside the workspace, isolated Python execution, and no `PYTHONPATH`
overlay. Each environment installed the wheel normally. These are package tests,
not the previous 72-case comparison harness.

The suite covers typed bindings/defaults/literals, admitted real Hamilton modifiers,
config alternatives, targeted parameterized ownership, immutable prepared shapes,
sequential/concurrent reuse, output and cleanup validation outside retry decisions,
timeouts/retry exhaustion, reverse shutdown, unexpected forward/cleanup cancellation,
repeated caller cancellation, and preservation of primary and secondary failures.
Generator/async-generator declarations fail before acquisition. Validated shutdown
functions are snapshotted so replacing an application's function code after driver
construction does not rewrite cleanup in existing plans.

Build artifacts and local test outputs are outside the repositories under
`/Users/owebeeone/limbo/evidence-build-cache/sdax-hamilton-package/`.
Qualified wheel SHA-256:

```text
sdax_hamilton-0.1.0a1-py3-none-any.whl
eb24f25b58193f190eb8a53555101bf582dc9e163c60345cfe5b61e25b33766d
```

Source distribution SHA-256:

```text
sdax_hamilton-0.1.0a1.tar.gz
1ee65c10fe7f7a4c70b015d5f91e9c209529a7aaa86fc6edb90a334ef7f0764a
```

The CI workflow defines an Ubuntu/Python 3.11, 3.12 and 3.13 matrix. It is intended
qualification coverage; adding that workflow does not mean it has run. No hosted
release or package publication is performed by that workflow.

## Remaining release gates

- Broaden compatibility only with new conformance cases; initial support remains
  the explicit [compatibility subset](../docs/Compatibility.md).
- Complete an independent review of the alpha API and its remaining ownership
  limits. Passing named cancellation cases is not proof of every interleaving.
- Qualify the CI Python/platform matrix before claiming support beyond local
  execution evidence.
- Freeze the public API and independently authorize any release/publication.

Deferred work includes partial-acquisition publication, cleanup between acquisition
attempts, dynamic Hamilton graphs, richer modifiers, typed result mappings,
application child-task ownership, sync offload and persisted execution state.

The earlier [comparison report](frontend-comparison-results.md) retains its own
provenance and private evidence links. Public package builds and tests must not
depend on that private archive.
