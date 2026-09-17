# Compatibility and limits

The alpha targets exactly `sdax==0.7.2` and `apache-hamilton==1.90.0`, on Python
3.11 or later. Local wheel tests pass on Python 3.11.14, 3.12.12 and 3.13.12;
other interpreter/platform combinations still require qualification. A dependency pin identifies
the implementation being integrated; it does not imply support for its entire API.

The compiler imports actual Hamilton declarations. It uses Hamilton's resolution
and graph machinery, then translates a restricted graph into an independent typed
binding/ownership representation and the existing SDAX runtime. It does not run
Hamilton `Driver.execute`, `AsyncDriver`, lifecycle adapters or remote executors.

## Declaration subset

| Declaration | Alpha boundary |
|---|---|
| Plain typed synchronous and asynchronous functions | Named parameters and annotated results; positional-only parameters, variadics, generators and async generators rejected. |
| Hamilton `config` | `when`, `when_not`, `when_in` and `when_not_in`; owned acquisitions cannot be replaced by config values. Custom callable predicates are deferred. |
| Hamilton `tag` | Admitted metadata; does not install Hamilton execution hooks. |
| Hamilton `inject` | Direct `value(...)` and `source(...)` bindings. |
| Hamilton `parameterize` | Direct expansion with explicit policy/ownership targets where ambiguous. |
| Frontend `execution` and `shutdown` | SDAX policy and ownership declarations; distinct from Hamilton decorators. |

This table is an allowlist, not a claim that every composition of these decorators
is supported. Unknown decorators and transformed bindings that lose required
contract information fail during construction or preparation. In particular:

- Grouped bindings, config-derived binding objects and optional parameters rebound
  to other source names are outside the initial subset.
- A merged Hamilton source binding cannot hide incompatible parameter contracts.
- Each selected sibling of a parameterized acquisition needs its own unambiguous
  shutdown assignment. Selecting a fully owned subset is allowed.
- Shutdown declarations cannot carry Hamilton transformations, take extra cleanup
  dependencies or duplicate ownership of one generated node.
- Resource extraction, `check_output` transformations, `pipe_output`, `mutate`,
  `does`, subgraphs and other unlisted modifiers are not qualified by this alpha.
  Support in earlier scratch probes is not a public compatibility commitment.

The compiler resolves annotations in the supplied modules. Unresolvable forward
references fail early. Application functions retain their original names across
multiple configured drivers; resolving Hamilton must not rename those functions.

## Type checking

The contract covers declared graph edges, defaults, admitted literal bindings,
config replacements, runtime inputs/overrides and, by default, returned values.
`Acquisition[T]` has an additional raw-versus-validated access distinction.

The initial type vocabulary is intentionally small:

| Form | Boundary |
|---|---|
| Concrete runtime classes | `isinstance` value checks and `issubclass` edge checks. |
| `Any`, `None` | `Any` deliberately weakens the guarantee; `None` is a value type. |
| `Union` and `A \| B` | Every possible producer branch must satisfy the consumer. |
| `Literal` | String, integer, boolean, byte-string and `None` literals; value and runtime type must match. |
| `list`, `dict`, `set`, `frozenset` | Admitted bare/parameterized forms; runtime checks inspect every element. |
| `tuple` | Fixed heterogeneous, variadic and empty tuple forms. |

Edge compatibility is conservative where container parameters differ. The
maintained tests define exact admitted cases. Protocols, `TypedDict`, arbitrary
generics/type variables and complete Python typing semantics are not promised.

These checks do not prove function bodies, lifetime safety, immutable values or
thread safety. Runtime class compatibility follows the implemented Python class
rules, rather than a separate nominal type system. Returned dictionaries are not
statically typed per output name. A bad annotation can be detected at runtime;
it does not become true through graph construction alone.

Callable results are resolved to values, including awaitables returned through
Hamilton wrappers. Intentionally passing an awaitable as data is unsupported.
Callbacks execute in the caller's event loop; synchronous work is not automatically
offloaded to a worker.

## Runtime boundaries

- Graphs are static after preparation. Dynamic expansion/collection, distributed
  execution, materializers and Hamilton caching adapters are not implemented.
- Reuse means one in-memory prepared processor, with separate invocation state.
  There is no persistent plan format, checkpoint or cross-run resource cache.
- Timeout is cooperative and per attempt, not a hard deadline or total-run budget.
- Acquisition retries are rejected when cleanup between attempts would be needed.
  Cleanup retries may repeat effects and require an author-supplied safe policy.
- Partial acquisition publication and ownership of arbitrary child tasks are not
  exposed. Returning resources before fallible dependent work is the supported
  lifecycle pattern.
- Mutable globals, closures, defaults, literals and config values remain shared
  application objects. Separate run contexts do not make these objects reentrant.

See [API](API.md) for detailed lifetime and failure contracts. Broader Hamilton
support should be added with explicit conformance and lifecycle tests, not by
silently falling back to Hamilton execution for unsupported nodes.
