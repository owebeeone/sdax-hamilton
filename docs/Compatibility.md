# Compatibility and limits

This development branch extends v0.1.0. The forms below describe current code,
not a new release. Final consolidated review and artifact qualification remain
release gates; progress is tracked in `dev-docs/Coverage-Execution.md`.

The experimental release targets exactly `sdax==0.7.2` and `apache-hamilton==1.90.0`,
with qualified Python versions 3.11–3.13. The initial alpha passed local macOS wheel
tests and Ubuntu CI on these versions; release artifacts must pass the wheel matrix
again before publication. Other interpreter/platform combinations still require
qualification. A dependency pin identifies
the implementation being integrated; it does not imply support for its entire API.

The compiler imports actual Hamilton declarations. It uses Hamilton's resolution
and graph machinery, then translates a restricted graph into an independent typed
binding/ownership representation and the existing SDAX runtime. It does not run
Hamilton `Driver.execute`, `AsyncDriver`, lifecycle adapters or remote executors.

## Declaration subset

| Declaration | Current development boundary |
|---|---|
| Plain typed synchronous and asynchronous functions | Named parameters and annotated results; positional-only parameters, variadics, generators and async generators rejected. |
| Hamilton `config` | `when`, `when_not`, `when_in`, `when_not_in` and custom callable predicates; predicates are trusted construction code and resolve once per declaration context. Owned acquisitions cannot be replaced by config values. |
| Hamilton `hamilton_exclude` | Excluded helpers need not be graph typed. An excluded declaration cannot own a frontend shutdown. |
| Hamilton `tag`, `tag_outputs`, `schema.output` | Resolved tags are retained on the isolated frontend node snapshot; they do not install Hamilton execution hooks. |
| Hamilton `cache`, `ray_remote_options` | Resolved cache and Ray tags are retained as inactive metadata. They do not enable caching, connect to Ray, or submit remote work. |
| Hamilton `inject` | `value(...)`, `source(...)` and direct list/dict `group(...)` bindings; original requirements and captured defaults survive source merging. |
| Hamilton `parameterize` and convenience aliases | Direct `parameterize`, `parameterize_values`, `parameterize_sources`, `parametrized`, `parametrized_input` and `parameterized_inputs` expansion with explicit policy/ownership targets where ambiguous. Legacy aliases retain Hamilton's deprecation behavior. |
| `extract_fields`, `unpack_fields`, `extract_columns`, `parameterize_extract_columns` | Projections borrow actual acquisitions; selected owned projections require `open()`. |
| `does`, `pipe_input`, `pipe`, `pipe_output`, `mutate` | Exact plain function helpers, checked actual bindings, sync/async execution and finite callable snapshots. Import-time mutation is captured at Driver construction. |
| `subdag`, `parameterized_subdag` | Explicit function/module sources, namespaces, configuration, inputs and external inputs; mount-specific ownership and recursive-cycle rejection. |
| `resolve`, `resolve_from_config` | Construction-time resolution once per actual context; returned modifiers pass the same exact-class admission. Hamilton's power-user setting remains required. |
| `model`, `dynamic_transform` | Configured model construction with bound state retained per Driver. Application state must be safe for the caller's intended reuse/concurrency. |
| `check_output`, `check_output_custom` | Mandatory fail gates remain enabled with `check_outputs=False`; raw/evidence nodes are internal and validation cannot be replaced through overrides/config. Library diagnostics omit validator payloads. |
| `load_from`, `save_to`, `dataloader`, `datasaver` | Registry selection captured once; adapter instances constructed per attempt. Explicit execution targets may select generated I/O steps; shutdown ownership remains on actual declaration calls. |
| Frontend `execution` and `shutdown` | SDAX policy and ownership declarations; distinct from Hamilton decorators. |

This table is an allowlist, not a claim that every composition of these decorators
is supported. Unknown decorators and transformed bindings that lose required
contract information fail during construction or preparation. In particular:

- `configuration(...)` is a subdag configuration binding, not a generic inject
  binding. Nested groups and forms rejected by pinned Hamilton remain rejected.
- Optional source defaults are retained by identity; a required consumer wins,
  and conflicting merged optional defaults are rejected.
- A merged Hamilton source binding cannot hide incompatible parameter contracts.
- Each selected sibling of a parameterized acquisition needs its own unambiguous
  shutdown assignment. Selecting a fully owned subset is allowed.
- Shutdown declarations cannot carry Hamilton transformations, take extra cleanup
  dependencies or duplicate ownership of one generated node.
- Only exact shipped modifier classes are admitted; arbitrary subclasses are not.
- I/O metadata must be independent of live resources. Selecting saver metadata
  permits cleanup after the saver returns; adapters must not hide resource aliases
  inside that metadata. Use explicit acquisition declarations for owned resources.

The compiler resolves annotations in the supplied modules. Unresolvable forward
references fail early. Application functions retain their original names across
multiple configured drivers; resolving Hamilton must not rename those functions.

## Optional static profiles

Importing and using an exact shipped optional decorator selects its pinned
dependency profile. Installed packages alone do not activate a profile. Test
extras provision these environments; base installation keeps optional dependencies
optional.

| Profile | Exact dependency versions | Boundary |
|---|---|---|
| Pandas `with_columns`, experimental `parameterize_frame` | Pandas 3.0.6 | Native expansion, captured bindings and projection ownership; experimental API remains experimental. |
| Polars eager/lazy `with_columns` | Polars 1.44.2 | Native column graphs; lazy results remain lazy. |
| Pydantic `check_output` | Pydantic 2.13.5 | Result is honestly typed as `Model \| dict[str, Any]`; no coercion. Nominal-model-only consumers/shutdowns are rejected. |
| Pandera `check_output` | Pandera 0.33.1, Pandas 3.0.6 | Validated producer returns concrete `pandas.DataFrame`. Generic `DataFrame[Schema]` consumer/shutdown annotations remain unsupported. |

Optional profiles currently have Python 3.12 local qualification. These bounded
profiles are not a claim of every possible decorator composition or unrestricted
backend/lifetime parity. Spark integration is still in progress.

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
| `TypedDict` | Required/optional fields, nested values and resolved forward annotations are checked as dictionaries. Extra keys are allowed. Edges accept the identical declaration, `dict`, `object` and compatible unions; structural equivalence between different declarations is not inferred. |

Edge compatibility is conservative where container parameters differ. The
maintained tests define exact admitted cases. Protocols, arbitrary
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
- Hamilton 1.90.0 can probe/import installed default-validator packages, including
  Pandera, during its own import even with registry autoload disabled. These are
  trusted dependency imports. Cache/Ray metadata does not activate backend execution;
  the base test profile runs with optional packages unavailable.

See [API](API.md) for detailed lifetime and failure contracts. Broader Hamilton
support should be added with explicit conformance and lifecycle tests, not by
silently falling back to Hamilton execution for unsupported nodes.
