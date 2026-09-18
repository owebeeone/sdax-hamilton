# Validation Qualification Safety Review A6a

## Disposition

The frozen E correction and V representation helpers pass this bounded safety
review. Public admission remains gated: neither family is added to public
`_SUPPORTED` by this snapshot, and V declaration/modifier dispatch is supplied
only by the temporary qualification runner.

## Mandatory validation and diagnostics

The raw producer, validator evidence and public gate remain distinct graph roles.
Raw and evidence nodes cannot be selected; raw, evidence and gate nodes cannot be
replaced by configuration or overrides; and an unrelated declaration cannot
consume a validation-internal edge. These checks occur before application
callbacks. The mandatory gate remains active when `check_outputs=False`.

A validation failure occurs after the raw producer has succeeded, so it does not
retry that producer. A failed owned validation releases its raw acquisition once.
Pipeline helpers and outer declarations retain separate raw owners and shutdowns;
default and explicit public shutdown targets map to the corresponding raw call
once.

Warnings, errors and `DataValidationError` carry only the node, validator,
status and level. Validator diagnostics and raw synthetic sentinels do not enter
library logs or raised validation text. An exception raised by user validator
code reaches the caller as the original object. Async validator identity and
parameterized target selection remain intact.

## Optional runtime representations

The Pydantic helper advertises the actual `Model | dict[str, Any]` representation
on the raw, evidence and gate edges. Valid model and dictionary objects retain
identity. A possible dictionary cannot flow into a nominal model consumer. A
shutdown accepting the union releases either raw representation once, while a
nominal `Acquisition[Model]` rejects before effects.

The Pandera helper advertises concrete `pandas.DataFrame`. A concrete dataframe
shutdown retains and releases the original frame. Generic
`DataFrame[Schema]` consumer and shutdown annotations remain unsupported until a
schema-aware edge contract is separately qualified.

The added optional imports occur only after an exact already-loaded shipped
modifier selects the pinned Pydantic or Pandera profile. Subclasses and impostors
remain unsupported. Hamilton's previously documented eager optional Pandera
probe is still an upstream baseline exception; this change adds no process-global
import hook or log filter and does not broaden that exception.

## Frozen evidence

- Base commit:
  `3a606071261a3462dff869bcd40952480b515de6`
- `src/sdax_hamilton/_hamilton_validation.py`:
  `0eade18e115d97ab55610ddd15aa63807f52a038b942940723775bd83d8ae9da`
- `src/sdax_hamilton/_hamilton_provenance.py`:
  `19fd8e964e9b039fdf80269ee6296fcdcc1049e61674dff7be3b4ec22fd11e8d`
- `tests/test_validation.py`:
  `b326e84791d38275310d1e1ab60bcc7faab9f8e34591f4cef8f549857878883c`
- `tests/test_validation_profiles.py`:
  `e2c28f5a54358fb6af8ec4605c9bed85f8a35f83ba965398400ab388ee9bbab3`
- `dev-docs/Decorator-Support-Inventory.md`:
  `2f07607dbd414f2775248c8d40ccafaa7a15d216e9f9f7740910cac59bdedee8`

Independent verification produced 21 passing exact E admission tests. The base
suite excluding E/V produced 316 passes and one skip. The Pydantic profile
produced eight passes and six skips; the Pandera profile produced six passes and
eight skips. Targeted mypy and Ruff checks and `git diff --check` passed.

The profile runs use `/tmp/sdax_hamilton_v_overlay_runner.py`. This verdict
qualifies the correction, runtime representations and exact profile gate design.
It does not claim a permanent V production-dispatch hook or public activation.
