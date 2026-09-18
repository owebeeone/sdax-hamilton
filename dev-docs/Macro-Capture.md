# Macro binding capture for phase C

This note records the C-family construction helper before compiler admission.
It is not a public compatibility claim: `does`, `pipe_input`, `pipe`,
`pipe_output`, and `mutate` remain outside the frontend's admitted declarations
until P2 provenance capture and the root compiler integration land.

`snapshot_copied_macro_bindings()` operates only on a declaration already copied
by `hamilton_compat._copy_function`. P2 supplies its memoized plain-function
copier so direct helper execution snapshots code, defaults, keyword defaults,
annotations, and function metadata while retaining globals and closure cells.
Arbitrary callable instances remain the original object. For exact pinned classes it copies
`does.argument_mapping`, each pipeline modifier's `transforms` tuple, every
`Applicable` argument/keyword container and direct source/value dependency
metadata. It preserves literal payloads, globals, closure cells, and stateful
instance identity. It does not recursively copy or resolve decorators carried
by a helper function. A user mutation after construction therefore cannot
redirect a copied source binding, replacement argument mapping, or plain helper
function code/defaults.

The helper reconstructs Hamilton's four built-in per-step configuration selectors
(`when`, `when_not`, `when_in`, `when_not_in`) from their finite captured mapping.
It copies the selector's list/tuple/set metadata containers and preserves other
application values. Custom resolver objects and unknown closure layouts fail
before expansion. This is intentionally version-coupled to 1.90.0 and covered by
the enclosing frontend version boundary.

`mutate` runs at import time: it adds an `Applicable` to the target function's
`pipe_output` and marks the mutator `hamilton_exclude`. The copied target pipeline
is therefore the capture input; the excluded mutator creates no graph node.

P2 owns the construction-local provenance wrappers. When it integrates this
helper, it must mark an owned `does` wrapper as the actual declared call, input
and output pipeline steps as derived calls, output raw as the declared call, and
the final output identity as borrowing the raw owner. The helper does not retain
role records or introduce a second graph.

Hamilton's `does` wrapper is synchronous even when its replacement is async, so
Hamilton's `AsyncDriver` returns the coroutine as data. SDAX's existing callback
resolution awaits it. The characterization test records this deliberate frontend
behavior; it must remain explicit in C compatibility documentation if admitted.
