# Phase E/V validation qualification review — A6b

## Verdict and boundary

Proceed with the frozen phase E validation foundation and the Pydantic/Pandera
runtime-representation rules. This is a bounded pass for the private compiler
hooks and profile contracts. Public E admission and product wiring for optional V
profiles remain integration gates; V was exercised through the explicit temporary
activation runner rather than added to public admission in this snapshot.

The reviewed snapshot is based on commit
`3a606071261a3462dff869bcd40952480b515de6`. Frozen hashes are:

- `_hamilton_validation.py`:
  `0eade18e115d97ab55610ddd15aa63807f52a038b942940723775bd83d8ae9da`
- `_hamilton_provenance.py`:
  `19fd8e964e9b039fdf80269ee6296fcdcc1049e61674dff7be3b4ec22fd11e8d`
- `test_validation.py`:
  `b326e84791d38275310d1e1ab60bcc7faab9f8e34591f4cef8f549857878883c`
- `test_validation_profiles.py`:
  `e2c28f5a54358fb6af8ec4605c9bed85f8a35f83ba965398400ab388ee9bbab3`
- `Decorator-Support-Inventory.md`:
  `2f07607dbd414f2775248c8d40ccafaa7a15d216e9f9f7740910cac59bdedee8`

My independent runs passed all 21 E overlay tests, eight Pydantic tests with six
profile skips, and six Pandera tests with eight profile skips. The diff check was
clean. The worker also reported the base suite, Ruff and mypy clean.

## Architecture assessment

Hamilton constructs and captures each exact validator before the correction
runs. The correction reads that same validator object from the generated evidence
callable and replaces only the final gate action that would otherwise render raw
validation payloads. It neither resolves validators again nor invokes their
validation callback twice. Evidence nodes still execute Hamilton's callable and
the final gate consumes those results.

Gate diagnostics contain the node, validator identity, status and importance but
omit raw values, validator result details and exception formatting. Mandatory
fail validation remains an ordinary graph dependency and therefore still runs
when `check_outputs=False`. A downstream validation failure does not retry the
upstream acquisition. Warn validation returns the original value identity with a
minimal warning. User validator exceptions retain their original identity through
the scheduler's failure group.

The provenance hook preserves the incoming declaration, public name, actual-call
identity and nonempty input contracts on the validation raw node. Evidence and
gate nodes receive their internal roles and cannot be selected or replaced to
bypass validation. Targeted parameterized outputs remain isolated; extraction in
both decorator orders and a targeted pipeline helper retain the correct owner,
policy and shutdown route. Success and failure witnesses release each raw
acquisition exactly once.

Pydantic's admitted runtime representation is the declared model or
`dict[str, Any]`, matching the shipped validator's documented identity-preserving
behavior. The generated raw, evidence input and gate all advertise that union.
Valid model and dictionary instances retain identity. A nominal model consumer or
`Acquisition[Model]` shutdown is rejected before effects because a valid raw value
may be a dictionary; an owned union shutdown receives and releases the exact raw
object once.

Pandera validation advertises the concrete `pandas.DataFrame` runtime class while
the copied declaration keeps `pandera.typing.DataFrame[Schema]` for Hamilton's
schema construction. Concrete consumers and shutdowns are admitted. Generic
schema-parameterized consumers and shutdowns remain rejected until schema-aware
edges are separately qualified.

Optional imports occur only after an exact already-loaded shipped modifier class
identifies the Pydantic or Pandera profile. The profile versions are checked before
the normalization path imports those dependencies. No validator registry,
alternate schema system, coercion, copied validation algorithm or second runtime
graph was introduced.

## Remaining gates

The optional activation runner is evidence, not product admission. Final wiring
must reuse exact-class profile identification and the existing contract checker,
and must retain the delayed-returned-modifier version check. A direct modifier can
encounter the pure distribution check during declaration validation and again
during temporary instrumentation; avoid adding persistent cache or registry state
solely to optimize that harmless check. Public E/V claims still require the final
integrated admission and composition run.
