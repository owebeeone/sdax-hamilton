# Bindings Qualification Safety Review A6a

## Disposition

The frozen phase-B binding and extraction foundation passes this bounded safety
review for integration. This is not a public-family activation verdict. The
real-Driver qualification file supplies a finite private `_supported` extension
for the extraction families; the production public `_SUPPORTED` set remains
closed.

## Original input contracts

The compiler snapshots the copied modifier's exact finite binding containers and
captures contracts from the original declaration's resolved hints and signature
before Hamilton expands the node. Every original consumer requirement is retained
in the existing `InputSpec`. A required consumer wins over optional consumers of
the same source. Optional defaults are retained only when all candidates are the
same application object; conflicting default objects reject during construction.

Captured output names must correspond exactly to Hamilton's generated raw calls.
Missing or colliding outputs fail closed. Contracts attach only to those matched
raw calls; `parameterize_extract_columns` extras and extraction outputs remain
projections. The shared namespace handoff preserves the complete requirement
tuple and default, including the maintained `low.component.shared` regression.

Invalid literals, mutated configuration dependencies, nested groups and lost
generated outputs reject before application callbacks. Runtime checks apply the
original requirement conjunction to external inputs, overrides, configuration
replacement and generated values even when output checking is disabled.

## Ownership and compatibility

Extraction keeps the incoming declaration, role, actual-call and ownership facts
on the generated raw node. Projections borrow that raw owner. Maintained Driver
cases prove the raw acquisition remains live through projection and releases the
original value exactly once, including invalid raw output.

The pinned Hamilton release rejects `None | list[...]` and
`None | dict[...]` grouped annotations at decoration because its own optional
unwrapping selects the first union argument. The frontend preserves that upstream
rejection and does not normalize those reversed forms independently. The admitted
`list[...] | None` and `dict[...] | None` forms retain Hamilton's behavior.

An omitted captured default is available through ordinary `prepare()`. Supplying
that optional source explicitly uses the existing
`prepare(optional_inputs=[...])` shape declaration. This review found no P4
selection change was required.

## Frozen evidence

- Base commit:
  `3a606071261a3462dff869bcd40952480b515de6`
- `src/sdax_hamilton/_hamilton_bindings.py`:
  `f24b566cda1c8071f0bf66e231f6828b84c23e6e5359590a14d92f94d7bf9856`
- `src/sdax_hamilton/_hamilton_provenance.py`:
  `91a7b308166642428e7b2ad6714c110f1c2b416b4f5613baa660df6f9610cfb5`
- `src/sdax_hamilton/hamilton_compat.py`:
  `d857d2ebee904b414fa7797a00fb406b1b5a7e2680f3914207e13b42626dd54e`
- `tests/test_binding_contracts.py`:
  `3d054b8497d34747e12f1d3e594cdf356c0841fa96939d278c7e08ba974974ba`
- Provisional `tests/test_bindings_extraction.py`:
  `2242342c667e4327605c4300802a501c616d0640f675ae6997d05524c94c5f37`
- `tests/test_compiler.py`:
  `1e178f6248176590f6f87d4cc87980be9dc8b4f91db263feb52b640aca6c9d25`

Independent verification matched all six file hashes. The binding and extraction
set passed 52 tests, the compiler set passed 36 tests, and the full clone suite
passed 341 tests with three optional-profile skips. Mypy passed on all three
changed source files; Ruff and `git diff --check` also passed.

