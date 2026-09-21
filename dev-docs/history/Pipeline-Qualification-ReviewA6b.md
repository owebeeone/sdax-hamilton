# Phase C pipeline production review — A6b

## Verdict and boundary

Proceed with the frozen phase C production overlay as the selected pipeline-step
producer for the shared input-contract transport seam. This is a bounded pass for
the private construction path. It does not approve public admission of `does`,
`pipe`, `pipe_input`, `pipe_output` or `mutate`, and it does not replace the
remaining integrated C composition gate.

The reviewed snapshot is based on commit
`08be6fb4b159fee856def48c35209b0a90186e7f`. Its tracked-diff SHA-256 is
`3fcdcb8738be2b74e1b20eb744c0b9b930d7c007471f4b7a49c0e332c0e032e3`.
The reviewed file hashes are:

- `_hamilton_pipeline.py`:
  `1f10424354856a4da2fd4aeedf7a343c5c2632a17e3d07a6bc723a62068e45d1`
- `_hamilton_provenance.py`:
  `d9212ca638620c3d308d60bac47660847a775f2d00c8786e05e8d92a8198e99a`
- `test_macro_compiler_qualification.py`:
  `1b631ce2f4146c3ab774f83e624a9fcb44a539186102c40972027914d0cf22e5`
- `test_pipeline_correction.py`:
  `e605cf54866c36c5a9a09e0934bbb72f9329e55943a10c9d8650bdb9c3ed1770`

The overlay qualification reported 22 passing C tests. The macro/correction set
reported 23 passing tests with the one expected closed-public-admission case
deselected. Ruff and mypy over the changed source files were clean. Those runs
used the shared transport seam and a finite test-only admission overlay. The
standalone clone intentionally predates that seam and keeps public admission
closed, so it is not by itself a runnable integrated-family snapshot.

## Architecture assessment

`selected_step_input_contracts()` consumes the `upstream_inputs` returned by the
single native `Applicable.bind_function_args()` invocation that Hamilton already
uses for the selected step. It does not evaluate configuration selectors again,
interpret a pipeline separately, scan a registry or construct another graph. The
capture hook attaches the resulting existing `InputSpec` objects to the selected
step fact, and the three provenance changes only pass that map into the shared
`_remember()` transport. The exact key-set comparison against the generated
Hamilton node fails closed if pinned expansion changes its dependency names.

The first reviewed draft allowed the last optional consumer of a merged source to
overwrite an earlier required consumer. The frozen correction reuses B's sole
`_merged_default()` authority. Any required selected parameter makes the merged
source required, independent of declaration order. Optional consumers retain a
default only when every candidate is the same object; conflicting optional
defaults fail before execution. `requirements[-1]` matches Hamilton 1.90's
last-declared type after `Node.reassign_inputs`, while the tuple retains every
original consumer contract for SDAX validation. Driver witnesses cover both
required/optional orders, identical mutable defaults, conflicting defaults,
external inputs and overrides, and rejection before the helper or downstream
callback runs. A runtime type failure after an upstream acquisition also proves
that the raw owner is still released exactly once.

Literal-bound parameters remain governed by the existing selected-step literal
preflight and do not become graph dependency contracts. Hamilton can have an
upstream source alias equal a separately literal-bound parameter name; its pinned
wrapper then applies its own collision behavior. The overlay retains the emitted
Hamilton callable and captures only the dependency declared in
`Node.input_types`, which preserves that behavior. Treating the literal as a
dependency default here would invent a contract that Hamilton did not emit.

No additional Hamilton version check, contract registry, binding executor,
intermediate representation or runtime graph was introduced. The enclosing
compiler version boundary remains authoritative, and B's helper remains the only
merged-default implementation.

## Remaining gates

Public `_SUPPORTED` admission remains closed. Before phase C can be advertised,
the integrated family snapshot still needs its finite public qualification and
composition tests. D0 must also demonstrate a real namespaced pipeline carrying a
nonempty original contract through the shared ordered namespace handoff. The
transport seam's direct two-type witness proves the rename invariant, while this
C snapshot proves nonempty producer facts; neither alone proves their integrated
composition. Existing restrictions also continue to apply: pipeline helpers and
`does` replacements must be exact plain functions, and an undiscovered external
pipeline helper fails before runtime effects.
