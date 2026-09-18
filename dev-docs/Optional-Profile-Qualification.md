# Optional profile qualification

All five profiles now use ordinary public Driver admission; their temporary
test admission fixtures have been removed. Installed-wheel qualification passes
for all five profiles on Python 3.12. QC remains open for consolidated review.
The focused source results and complete installed-wheel results are recorded below.

| Profile | Candidate versions | Current evidence |
|---|---|---|
| Pandas / experimental frame | Pandas 3.0.6 | 5 focused cases pass, including public Driver graph/value comparison |
| Polars eager/lazy | Polars 1.44.2 | 7 focused cases pass, including public Driver composition and preserved lazy output |
| Pydantic | Pydantic 2.13.5 | 9 focused cases pass, including model/dict representation and delayed validation |
| Pandera | Pandera 0.33.1, Pandas 3.0.6 | 10 focused cases pass, including concrete dataframe representation and delayed validation |
| Classic local Spark | PySpark 4.0.1, Pandas 2.3.3, PyArrow 21.0.0, Java 21 | 8 public Driver cases and 8 pure guard cases pass; 5 stock-Hamilton characterizations pass |

Complete installed-wheel suites, run outside the source repository without
`PYTHONPATH`: Pandas **439 passed / 22 skipped**, Polars **441 / 23**, Pydantic
**443 / 15**, Pandera **444 / 14**, Spark **447 / 22**. Skips belong to other
profiles. The Polars schema-resolution performance warning and Pandera import
deprecation warning originate in the pinned dependency paths.

The four non-Spark profiles ran in the shared static-profile environment; Spark
ran in its separate compatible environment. Isolated per-profile Ubuntu CI jobs
are configured but have not run for this local checkpoint. The Spark stock fixture
now distributes its public witness module with `addPyFile`, so Python workers do
not depend on pytest's driver-side import path.

All use Apache Hamilton 1.90.0 and SDAX 0.7.2. Profile tests are product fixtures;
environments and dependency/build caches live outside repositories. The base
environment is unchanged. Spark needs its own environment: PySpark 4.0.1's
Pandas-on-Spark import fails against Pandas 3.0.6. The compact jdk4py 21 runtime
lacks Spark's requested `jdk.incubator.vector` module; the successful smoke used
the installed full OpenJDK 21 runtime. Neither failure warrants a product patch.

## Activation boundary

An explicitly used, exact shipped decorator class selects its profile. Looking
up a known module/attribute in `sys.modules` must not import a backend, invoke a
module `__getattr__`, or scan a plugin registry. Merely installing/importing a
backend does not activate it. A subclass or another class with the same name is
not accepted. The compiler still owns family admission; the private recognition
helper alone grants none. Verify pinned distributions only when an admitted
modifier requests a profile. This avoids a second public Driver configuration
mechanism and contradictory decorator/profile settings.

The independent architecture reviewer approved this boundary. Hamilton's own
upstream import probes remain subject to the previously documented limitation;
this is a restriction on additional frontend imports.

## Spark implementation boundary

The implementation accepts a caller-owned classic local Spark session and lazy
plan construction with exact `with_columns`, `select` and nested
`require_columns`. It rejects SDAX acquisition/shutdown/borrow placements and
non-default retry/timeout policies in the Spark chain before effects. Spark
Connect, background/remote work and a Spark cancellation bridge are outside this
profile. Standalone `require_columns` and Spark decorators inside Hamilton subdags
are rejected. Nested UDF execution/shutdown declarations are rejected before
native expansion, including declarations hidden by the generated wrapper.

Trusted decorated functions must build plans without starting actions or
background jobs. Static decorator admission cannot prove that arbitrary Python
code follows this contract. Maintained fixtures must distinguish plan building
from an explicit later materialization and stop their local session in `finally`.

A synchronous Spark action invoked inline blocks the event loop: SDAX timeout,
cancellation and cleanup are delayed until that call returns. This defeats timely
cancellation; it does not by itself prove concurrent early cleanup. A lazy result
or externally launched job can outlive the SDAX call, so its caller must retain
the session and other required resources. `open()` alone does not establish Spark
job termination. Owned/background execution needs separate stop-and-join evidence
before any stronger support claim.

This implements the earlier safety review's bounded feasibility contract;
consolidated review remains pending. Local witnesses cover stock/frontend
graph and value parity, no job during construction, explicit action results,
and unsafe policy/ownership rejection before effects. The synchronous-action
cancellation limitation remains a documented constraint. QC cannot claim
unrestricted Spark lifecycle parity.
