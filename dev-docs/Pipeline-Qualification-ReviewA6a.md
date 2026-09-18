# Pipeline Qualification Safety Review A6a

## Disposition

The frozen phase-C production overlay passes this bounded safety review for
integration over the shared input-contract seam. This is not a public-family
activation verdict: public `_SUPPORTED` remains unchanged, and the qualification
tests use an exact private admission harness.

The selected pipeline-step hook observes Hamilton's already selected and bound
exact `Applicable` once. It neither evaluates selectors again nor replays a
lifecycle. Each generated helper retains its original declaration identity, so a
direct call and a generated call receive distinct policy, acquisition and
shutdown state even when they originate from the same helper.

## Input contracts and defaults

Hamilton can merge several helper parameters onto one upstream source while its
generated node retains only one declared type and default. The overlay records
every original helper requirement in the existing `InputSpec`. A required
consumer forces `MISSING` regardless of parameter order. Optional defaults are
retained only when every candidate is the same application object; conflicting
defaults reject during construction. Literal-bound parameters remain under the
existing selected-step literal preflight and do not become graph inputs.

The full requirement conjunction is therefore enforced for external inputs,
overrides and generated values. A maintained real-Driver case disables output
checking, lets an owned permissive raw producer return a bad value, and proves
that the selected helper and downstream declaration do not run while the raw
acquisition releases exactly once. `check_outputs=False` does not weaken the
consumer-call contract.

## Ownership and policy

The generated helper actual call retains the helper's ownership and execution
policy identity. The declaration raw node remains the explicit policy and
shutdown target for an output pipeline; the public output borrows it and cannot
be replaced. Maintained execution checks prove independent shutdown of direct
and generated helper calls, one release per acquisition, mutation isolation for
helper code and bindings, typed `does` replacement/default behavior, and the
snapshot of an import-time `mutate` pipeline.

The U1 helper no longer performs its own version lookup. This is safe only within
the reviewed production path: `compile_modules()` calls the central exact
Hamilton and SDAX version guard before copying a declaration or applying the
correction. The correction remains private and has no separate public entry.

## Frozen evidence

- Base commit:
  `08be6fb4b159fee856def48c35209b0a90186e7f`
- Tracked overlay diff SHA256:
  `3fcdcb8738be2b74e1b20eb744c0b9b930d7c007471f4b7a49c0e332c0e032e3`
- `src/sdax_hamilton/_hamilton_pipeline.py`:
  `1f10424354856a4da2fd4aeedf7a343c5c2632a17e3d07a6bc723a62068e45d1`
- `src/sdax_hamilton/_hamilton_provenance.py`:
  `d9212ca638620c3d308d60bac47660847a775f2d00c8786e05e8d92a8198e99a`
- `tests/test_macro_compiler_qualification.py`:
  `1b631ce2f4146c3ab774f83e624a9fcb44a539186102c40972027914d0cf22e5`
- `tests/test_pipeline_correction.py`:
  `e605cf54866c36c5a9a09e0934bbb72f9329e55943a10c9d8650bdb9c3ed1770`

I merged the frozen C overlay with the exact shared input-contract seam in an
external qualification copy. All 22 phase-C Driver tests passed. The macro-capture
and U1 correction set passed 24 tests. Targeted mypy and Ruff checks passed. A
separate direct probe confirmed required-wins behavior, the complete requirement
conjunction, preservation of an identical default by object identity, and
conflicting-default rejection.

The provisional C provenance copy predates unrelated discovery work, so its
broad-suite collection result is not integration evidence. Final integration
must retain the current shared discovery source and D0 namespace handoff checks.
