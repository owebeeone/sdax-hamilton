# Phase B bindings and extraction review — A6b

## Verdict and boundary

Proceed with the frozen phase B production snapshot. The implementation makes
the existing binding helper the sole authority for binding capture and merged
defaults, then seeds the shared `InputSpec` provenance transport. It does not add
another binding executor, contract representation, intermediate graph or runtime
dispatch path. This is a bounded pass for B production and its finite private
qualification; public family admission and the final integrated family run remain
separate gates.

The reviewed snapshot is based on commit
`3a606071261a3462dff869bcd40952480b515de6`. Frozen hashes are:

- `_hamilton_provenance.py`:
  `91a7b308166642428e7b2ad6714c110f1c2b416b4f5613baa660df6f9610cfb5`
- `hamilton_compat.py`:
  `d857d2ebee904b414fa7797a00fb406b1b5a7e2680f3914207e13b42626dd54e`
- `test_binding_contracts.py`:
  `3d054b8497d34747e12f1d3e594cdf356c0841fa96939d278c7e08ba974974ba`
- `test_bindings_extraction.py`:
  `2242342c667e4327605c4300802a501c616d0640f675ae6997d05524c94c5f37`
- `test_compiler.py`:
  `1e178f6248176590f6f87d4cc87980be9dc8b4f91db263feb52b640aca6c9d25`

The final clone suite passed 341 tests with three optional-profile skips. The
focused binding and extraction set passed 52 tests, and the compiler set passed
36 tests. Ruff, mypy over the changed source, and the diff check were clean.

## Architecture assessment

`_instrument_bindings()` delegates capture and container isolation to
`_hamilton_bindings.capture_bindings()` and
`snapshot_binding_containers()`. Those helpers interpret the exact admitted
Hamilton binding modifier classes. The older compatibility-layer validator and
the shallow parameterize snapshot in `_copy_function()` were removed, leaving one
binding authority and one snapshot path. Construction records the resulting
existing `InputSpec` objects on the generated facts; lowering continues through
the shared input-contract transport.

Optional list and dictionary groups follow Hamilton 1.90's own Optional
unwrapping convention before the exact list/dict origin check. Required and
optional consumers merged onto one external source use the shared
`_merged_default()` rule: any required consumer makes the source required;
optional defaults survive only when they are the same object; conflicting
defaults reject before execution. The requirement tuple retains every original
consumer contract while its exposed type follows the pinned Hamilton edge.

Configuration can rename the declaration before an `inject` or
`parameterize_extract_columns` modifier emits nodes. The frozen implementation
maps captured declaration keys to the exact generated entry names and fails on
loss or collision. Real Driver witnesses cover config with both modifier forms,
so the contracts do not depend on the original function name after Hamilton has
selected and renamed the declaration. Native selected binding remains
authoritative; literal bindings do not become graph inputs or invented contracts.

The extraction hook covers the exact `extract_fields`, `extract_columns` and
`unpack_fields` classes. It preserves the incoming declaration, roles and
contracts on the raw node and marks generated projections as borrowing aliases of
that same owner. Success and invalid-value witnesses show that an owned raw
acquisition closes once and that projections do not become independent owners.
The emitted Hamilton callables, names, edges, tags and values remain the native
ones.

No additional Hamilton version guard, global registry, alternate validator or
copied Hamilton expansion algorithm was introduced. The enclosing compiler
version boundary and shared contract checker remain authoritative.

## Remaining gates

The qualification tests use the existing finite private admission seam; public
support remains closed until the final family qualification removes those
fixtures. D namespace composition must retain these nonempty contracts across its
ordered handoff, and F must demonstrate B contracts reaching a real SaveTo edge.
Optional-column and validation compositions likewise remain claims of their
respective integrated gates rather than this bounded B snapshot.
