# I/O Qualification Safety Review A6a

## Disposition

The frozen phase-F I/O overlay passes this bounded safety review for integration
over the shared binding and provenance foundation. This is not a public-family
activation verdict. The qualification tests add the exact four I/O modifier
classes only through a process-local test harness; public `_SUPPORTED` remains
closed.

## Generated roles and ownership

`load_from` and `dataloader` preserve Hamilton's raw metadata tuple and public
data projection as separate nodes. A `dataloader` declaration that owns a
shutdown attaches ownership and release to the raw tuple call; its projection
borrows that raw owner and requires `open()`. A registry `load_from` raw remains a
synthetic value and does not acquire declaration ownership by itself. A normal
consumer may still acquire the projected value and release its own exact raw
identity once.

`datasaver` remains one actual effect declaration. A `save_to` sink is a fresh
metadata value with `borrows=False`. Its ordinary data dependency keeps an owned
producer alive through `save_data`, after which that producer releases exactly
once before the metadata returns. This relies on the same bounded trusted-code
contract as an ordinary Hamilton function: a saver must not publish a live
producer or resource alias inside its metadata.

Validation, extraction, binding and pipeline transforms forward a synthetic
adapter policy-target fact only on their corresponding raw call. Evidence,
gates and projections do not become policy targets. Shutdown selection remains
restricted to actual declaration calls, so a fresh `save_to` sink cannot be
made an acquisition owner.

## Adapter and policy boundaries

The selected registry class and its literal bindings are snapshotted during
Driver construction. Later registry mutation does not change an existing
Driver. Invalid literals, configuration bindings and missing adapter arguments
reject before adapter construction or application effects.

Default execution policy still attaches to the declared consumer or producer.
An explicit policy may name the exact `load_from` raw loader node or `save_to`
metadata sink. The selected adapter instance is constructed inside that timed,
retried node callback on every attempt. The maintained loader witness observes
`construct/load/construct/load`; the saver witness observes the producer once,
then `construct/save/construct/save`. Retry therefore does not replay an
already-completed producer.

The final composition witness carries a nonempty, namespaced binding contract
through `parameterized_subdag` and `save_to`. It retains
`InputSpec(int | str, default=3, requirements=(int, int | str))`. An explicitly
supplied invalid optional value rejects before either the producer or saver runs.

## Frozen evidence

- Base commit after the shared B sync:
  `67db48504c760c7d3e870adf0d32709957f91c2b`
- `src/sdax_hamilton/_hamilton_provenance.py`:
  `2e35d66db93c7c2b535a996053ac4bd1bd0c51349ae74179c94c7c03ab30cf6c`
- `src/sdax_hamilton/hamilton_compat.py`:
  `28796668b3af5861f6b5fde1610160fd25538fb97217dc0c41cdfddaa1738aac`
- `tests/test_io_driver.py`:
  `e10052c3a07792ccf52d723d3294e6455caf2b50818c30ffc3840c363c3e8c5e`
- `dev-docs/Loader-Correction.md`:
  `2b1fc8c8b03de503c528126f1c1dfafd4384d5250b626f7a7e5740243c4b2b90`

Independent verification matched all four frozen file hashes. The I/O Driver,
loader-correction and I/O-contract set passed 36 tests. The full clone suite
passed 398 tests with 15 expected optional-profile skips. Targeted mypy and Ruff
checks and `git diff --check` passed.

