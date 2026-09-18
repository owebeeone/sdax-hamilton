# Hamilton 1.90.0 loader annotation correction

`LoadFromDecorator.get_loader_nodes()` in Apache Hamilton 1.90.0 creates a raw
loader node whose callable returns `(data, metadata)` and whose projection reads
element zero. Its declared raw type is nevertheless
`tuple[dict[str, Any], data_type]`. The reversed annotation makes the frontend's
structural raw-result check reject a correct loader result.

`sdax_hamilton._hamilton_loader.correct_load_from_annotations()` corrects only
that generated pair to `tuple[data_type, dict[str, Any]]`, and updates the
projection's input contract to the same corrected tuple. It retains the checked
raw result and checked projected value; it neither weakens either type nor
reorders runtime values.

The helper is private and has no independent version detection. Its compiler call
site must invoke it only after `hamilton_compat._check_version()` has verified
both the installed distribution and imported source are exactly 1.90.0, and only
for the exact generated pair or collection returned from a per-function path
already admitted as a `LoadFromDecorator`. Invoke it before that pair is merged
with unrelated declaration nodes. The helper verifies the raw/projection
relationship using the data-loader tags, their common loader identity, and the
projection input keyed by the raw node's full name. It does not infer a pair from
names, adapter registry state, or arbitrary tags. An admitted path with a
different generated shape raises `RuntimeError`; unadmitted tagged nodes,
including the similarly tagged `dataloader` output, are returned unchanged.
Already-correct pairs are returned unchanged.

This is a local compatibility boundary, not a Hamilton patch. It performs no
adapter lookup, construction, loader invocation, registry mutation, or I/O.
The installed copied-instance wrapper also reads the selected raw callable's
fixed Hamilton 1.90.0 defaults before returning its nodes. The captured
`AdapterFactory` supplies the already selected adapter class and the captured
literal map supplies values that Hamilton removed from generated node inputs.
The wrapper validates those literals against that class's required and optional
argument contracts with SDAX's supported runtime type checks. It does not
resolve an adapter again or construct one, so an invalid literal fails before
any adapter effect. In the pinned upstream source, the contract class methods
read dataclass fields and resolved type hints; Hamilton has already called them
while making the generated node. The preflight repeats that contract
introspection after selection to recover the erased literal types. Admitted
adapter contract methods must therefore retain Hamilton's normal pure,
no-I/O introspection behavior; this helper does not call `resolve_adapter_class`
or either factory creation method.
The copied exact `SaveToDecorator` uses the same bounded technique on its
generated saver node: it validates the selected `AdapterFactory`'s captured
literals before the node can construct a saver. It does not infer acquisition
ownership or change saver selection, target, metadata, or execution behavior.
Phase F remains responsible for admitting I/O decorators, preserving Hamilton's
adapter precedence, snapshotting selected adapter identity, and qualifying
execution effects. Retire this helper when the pinned Hamilton version is
upgraded and its source plus the maintained regression cases show that the
generated raw and projection annotations are already correct. A version mismatch
must continue to fail closed through `hamilton_compat._check_version`; it is not
an instruction to apply this correction to another Hamilton release.
