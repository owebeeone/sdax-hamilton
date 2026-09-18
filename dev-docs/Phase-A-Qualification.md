# Phase A qualification: aliases, configuration, and metadata

This qualification covers only existing supported graph shapes with
`apache-hamilton==1.90.0` and `sdax==0.7.2`. It does not qualify recursive
declarations, extraction, grouped/config-derived bindings, plugin types, cache
execution, or Ray execution.

## Admitted surface

- Exact Hamilton classes `parameterize_values`, `parameterize_sources`,
  `parametrized`, `parametrized_input`, and `parameterized_inputs` reuse the
  existing parameterization validation and lowering path. The three legacy forms
  keep Hamilton's own deprecation behavior.
- Exact `config` instances may use a custom predicate. The predicate is trusted
  application construction code and resolves once for each declaration context;
  it is never replayed by plan preparation or invocation.
- Exact `hamilton_exclude` permits an excluded helper without graph annotations.
  An excluded declaration that owns a frontend shutdown fails at construction, so
  exclusion cannot erase an ownership obligation.
- Exact `tag`, `tag_outputs`, `schema.output`, `cache`, and
  `ray_remote_options` classes are lowered from Hamilton's resolved node tags.
  `NodeSpec.tags` is an isolated snapshot of that finite tag mapping. Hamilton's
  known list-valued tag containers are copied too, but are not recursively frozen;
  their elements and other tag values retain their application identities.

Cache and Ray tags remain data only. They neither enable caching nor import,
connect to, or submit work to Ray. Their runtime profiles remain K0/K/QK and
R0/R/QR work respectively.

## Evidence and retained boundaries

`tests/test_aliases_metadata.py` compares alias names, edges, types and metadata
with the shared stock-Hamilton oracle, checks custom-predicate count and excluded
ownership, and proves tagged calls remain local and uncached. The test uses public
fixtures only.

The obsolete `custom Hamilton config resolver unsupported` case was removed from
`tests/test_compiler.py::test_declarations_reject_before_execution`; it is replaced
by `test_custom_config_predicate_resolves_once_before_execution`. The remaining
negative declaration cases still cover unsupported decorators and bindings.
