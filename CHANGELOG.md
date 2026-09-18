# Changelog

## Unreleased

- Extend static graph compilation to Hamilton's binding/extraction, pipeline,
  recursive subgraph, delayed resolver/model, validation and I/O decorator families.
- Preserve parameter contracts and ownership through generated nodes; apply SDAX
  execution policies to explicit generated I/O targets.
- Add optional Pandas, Polars, Pydantic and Pandera profiles with pinned test
  environments and ordinary public Driver coverage.
- Retain cache and Ray declarations as inactive metadata. SDAX remains the sole
  graph orchestrator; these declarations do not enable their execution backends.

Consolidated review and final artifact qualification remain pending. Current
boundaries are documented in [Compatibility](docs/Compatibility.md).

## 0.1.0

First experimental PyPI release of the typed Hamilton frontend over SDAX.

- Reuse supported real Hamilton declarations (`config`, `tag`, `inject`,
  `parameterize`, `source`, `value`) with checked parameter/result bindings.
- Prepare once and reuse SDAX execution plans with separate invocation state.
- Declare per-attempt timeouts, retries and dependency-ordered shutdown without
  changing SDAX's minimal core API.
- Keep owned results alive inside `plan.open()` and retain primary/secondary
  failure diagnostics while draining cleanup.
- Correct the alpha's empty-tuple assignability bypass and cancellation races
  found during the independent implementation review.
- Publish tested wheels and source distributions through GitHub/PyPI trusted
  publishing, with artifact qualification on Python 3.11–3.13.

The API is experimental. Dependencies are pinned to `sdax==0.7.2` and
`apache-hamilton==1.90.0`. This is a restricted Hamilton frontend, not full
Hamilton execution compatibility. See [Compatibility](docs/Compatibility.md).
