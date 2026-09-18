"""Pinned correction for Hamilton's generated validation gate diagnostics."""

import inspect
import logging
from collections.abc import Collection
from typing import Any, get_args, get_origin

from hamilton import node
from hamilton.data_quality.base import DataValidationError, DataValidationLevel, DataValidator

logger = logging.getLogger(__name__)

_VALIDATION_PROFILES = frozenset(("pydantic", "pandera"))


def normalize_validation_annotation(annotation: Any, profile: str | None) -> Any:
    """Return the bounded runtime type used to validate one profiled declaration.

    The compiler calls this only after an exact optional modifier has selected and
    version-checked ``profile``. The original annotation remains on the copied
    declaration so Hamilton can construct its own schema validator.
    """
    if profile is None or profile == "pydantic":
        return annotation
    if profile != "pandera":
        raise ValueError(f"Unknown Hamilton validation profile: {profile}")

    # These imports are intentionally inside the explicitly selected optional
    # profile. Importing sdax_hamilton must not import either optional dependency.
    from pandas import DataFrame as PandasDataFrame
    from pandera import DataFrameModel
    from pandera.typing import DataFrame as PanderaDataFrame

    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if (
        origin is not PanderaDataFrame
        or len(arguments) != 1
        or not isinstance(arguments[0], type)
        or not issubclass(arguments[0], DataFrameModel)
    ):
        raise TypeError("Pandera validation requires DataFrame[DataFrameModel]")
    return PandasDataFrame


def correct_validation_representation(
    generated: Collection[node.Node], profile: str | None
) -> tuple[node.Node, ...]:
    """Make generated validation nodes advertise their true runtime value shape."""
    generated = tuple(generated)
    if profile is None:
        return generated
    if profile not in _VALIDATION_PROFILES:
        raise ValueError(f"Unknown Hamilton validation profile: {profile}")
    if len(generated) < 3:
        raise RuntimeError("Hamilton validation node shape changed")

    evidence_nodes = generated[:-2]
    gate, raw = generated[-2:]
    if profile == "pydantic":
        try:
            runtime_type = raw.type | dict[str, Any]
        except TypeError as exc:
            raise TypeError("Pydantic validation requires a model class annotation") from exc
    else:
        runtime_type = normalize_validation_annotation(raw.type, profile)

    def with_raw_input(entry: node.Node) -> node.Node:
        input_types = dict(entry.input_types)
        captured = input_types.get(raw.name)
        if captured is None:
            raise RuntimeError("Hamilton validation raw edge shape changed")
        _, dependency_type = captured
        input_types[raw.name] = (runtime_type, dependency_type)
        return entry.copy_with(input_types=input_types)

    corrected_evidence = tuple(with_raw_input(entry) for entry in evidence_nodes)
    corrected_gate = with_raw_input(gate).copy_with(typ=runtime_type)
    corrected_raw = raw.copy_with(typ=runtime_type)
    return (*corrected_evidence, corrected_gate, corrected_raw)


def _generated_validator(entry: node.Node) -> DataValidator:
    """Return the exact validator captured by Hamilton's generated callable."""
    parameter = inspect.signature(entry.callable).parameters.get("validator_to_call")
    if parameter is None or parameter.default is inspect.Parameter.empty:
        raise RuntimeError("Hamilton validation callable shape changed")
    validator = parameter.default
    if not isinstance(validator, DataValidator):
        raise RuntimeError("Hamilton validation callable did not capture a validator")
    return validator


def correct_validation_gate(generated: Collection[node.Node]) -> tuple[node.Node, ...]:
    """Replace only Hamilton's payload-revealing final validation action.

    ``BaseDataValidationDecorator.transform_node`` has already constructed the
    validators and generated callables. This function consumes those exact objects;
    it never resolves or constructs validators a second time.
    """
    generated = tuple(generated)
    if len(generated) < 3:
        raise RuntimeError("Hamilton validation node shape changed")
    evidence_nodes = generated[:-2]
    gate, raw = generated[-2:]
    gate_name = gate.name
    raw_name = raw.name
    validators = tuple((entry.name, _generated_validator(entry)) for entry in evidence_nodes)

    def final_node_callable(**kwargs):
        failures: list[str] = []
        for validator_name, validator in validators:
            result = kwargs[validator_name]
            if result.passes:
                continue
            level = validator.importance
            message = (
                f"Validation failed: node={gate_name}; validator={validator_name}; "
                f"status=failed; level={level.value}"
            )
            if level is DataValidationLevel.WARN:
                logger.warning(message)
            else:
                logger.error(message)
                failures.append(message)
        if failures:
            raise DataValidationError(failures)
        return kwargs[raw_name]

    return (*evidence_nodes, gate.copy_with(callabl=final_node_callable), raw)
