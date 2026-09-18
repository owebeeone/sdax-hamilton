# Optional profile qualification

These profiles are under qualification. Their dependency pins and private
recognition helper do **not** enable the corresponding decorators. QC remains
open until actual Driver, SDAX, composition and installed-package cases pass.

| Profile | Candidate versions | Current evidence |
|---|---|---|
| Pandas / experimental frame | Pandas 3.0.6 | Two stock-Hamilton characterizations pass; frontend integration pending |
| Polars eager/lazy | Polars 1.44.2 | Five stock characterizations pass, including lazy output and nested configuration; frontend integration pending |
| Pydantic | Pydantic 2.13.5 | Stock schema validation preserves model/dict identity; frontend representation integration pending |
| Pandera | Pandera 0.33.1, Pandas 3.0.6 | Stock dataframe identity/validation characterized; frontend schema typing integration pending |
| Classic local Spark | PySpark 4.0.1, Pandas 2.3.3, PyArrow 21.0.0, Java 21 | Local `local[2]` session/collect smoke passed; Hamilton plugin import passed; decorator/lifecycle gate pending |

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

## Spark contract to qualify

The initial candidate is a caller-owned classic local Spark session and lazy
plan construction. Qualify exact `with_columns`, `select` and nested
`require_columns`. Reject SDAX acquisition/shutdown/borrow placements and
non-default retry/timeout policies in the Spark chain before effects. Spark
Connect, background/remote work and a Spark cancellation bridge are outside this
profile.

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

This is the safety review's refined feasibility boundary, not an activated or
complete G3 implementation. Required local witnesses include stock/frontend
graph and value parity, no job during construction, explicit action results,
unsafe policy/ownership rejection before effects, and observed cancellation
limitations. QC cannot claim unrestricted Spark lifecycle parity.
