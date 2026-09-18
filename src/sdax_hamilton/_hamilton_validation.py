"""Pinned correction for Hamilton's generated validation gate diagnostics."""

import inspect
import logging
from collections.abc import Collection

from hamilton import node
from hamilton.data_quality.base import DataValidationError, DataValidationLevel, DataValidator

logger = logging.getLogger(__name__)


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
