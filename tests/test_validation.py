"""Hamilton validation gates preserve semantics without exposing diagnostic payloads."""

import gc
import inspect
import logging
import weakref

import pytest
from hamilton import node
from hamilton.data_quality.base import DataValidationError, DataValidator, ValidationResult
from hamilton.function_modifiers import check_output_custom

from sdax_hamilton._hamilton_validation import correct_validation_gate


class RecordingValidator(DataValidator):
    def __init__(
        self,
        name: str,
        importance: str,
        result: ValidationResult | BaseException,
    ) -> None:
        super().__init__(importance)
        self._name = name
        self.result = result
        self.values = []

    @classmethod
    def name(cls) -> str:
        return "recording"

    def applies_to(self, datatype: type[type]) -> bool:
        return True

    def description(self) -> str:
        return self._name

    def validate(self, dataset):
        self.values.append(dataset)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class AsyncRecordingValidator(RecordingValidator):
    async def validate(self, dataset):
        return super().validate(dataset)


def _generated(*validators: DataValidator):
    def result() -> int:
        return 1

    original = check_output_custom(*validators).transform_node(
        node.Node.from_fn(result), {}, result
    )
    return tuple(original), correct_validation_gate(original)


def test_correction_reuses_generated_validator_instances_and_preserves_shape():
    validator = RecordingValidator("validator", "warn", ValidationResult(True, "", {}))
    original, corrected = _generated(validator)

    assert [entry.name for entry in corrected] == [entry.name for entry in original]
    assert [entry.input_types for entry in corrected] == [entry.input_types for entry in original]
    assert corrected[0].callable is original[0].callable
    captured = inspect.signature(corrected[0].callable).parameters["validator_to_call"].default
    assert captured is validator


def test_corrected_callable_does_not_retain_hamilton_nodes():
    validator = RecordingValidator("validator", "warn", ValidationResult(True, "", {}))
    original, corrected = _generated(validator)
    references = tuple(weakref.ref(entry) for entry in (*original, *corrected))
    gate_callable = corrected[-2].callable

    del original, corrected
    gc.collect()

    assert all(reference() is None for reference in references)
    assert not any(
        isinstance(cell.cell_contents, node.Node) for cell in gate_callable.__closure__ or ()
    )


def test_mixed_warn_and_fail_diagnostics_are_data_minimal(caplog):
    secret = "SENTINEL-RAW-VALIDATION-DIAGNOSTIC"
    warning = RecordingValidator(
        "warning",
        "warn",
        ValidationResult(False, secret, {"payload": secret}),
    )
    failure = RecordingValidator(
        "failure",
        "fail",
        ValidationResult(False, secret, {"payload": secret}),
    )
    _, generated = _generated(warning, failure)
    warning_node, failure_node, gate, raw = generated
    raw_value = f"raw-{secret}"
    warning_result = warning_node.callable(**{raw.name: raw_value})
    failure_result = failure_node.callable(**{raw.name: raw_value})

    with caplog.at_level(logging.WARNING), pytest.raises(DataValidationError) as error:
        gate.callable(
            **{
                raw.name: raw_value,
                warning_node.name: warning_result,
                failure_node.name: failure_result,
            }
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    rendered += f"\n{error.value}"
    assert secret not in rendered
    assert gate.name in rendered
    assert warning_node.name in rendered
    assert failure_node.name in rendered
    assert "status=failed" in rendered
    assert "level=warn" in rendered and "level=fail" in rendered
    assert warning.values == [raw_value] and failure.values == [raw_value]


def test_custom_validator_exception_identity_is_unchanged():
    failure = RuntimeError("user validator failure")
    validator = RecordingValidator("failure", "fail", failure)
    _, generated = _generated(validator)
    evidence, _, raw = generated

    with pytest.raises(RuntimeError) as error:
        evidence.callable(**{raw.name: 1})

    assert error.value is failure


@pytest.mark.asyncio
async def test_async_validator_callable_and_identity_are_unchanged():
    result = ValidationResult(True, "accepted", {})
    validator = AsyncRecordingValidator("async", "fail", result)
    original, corrected = _generated(validator)
    evidence, gate, raw = corrected

    assert evidence.callable is original[0].callable
    evidence_result = await evidence.callable(**{raw.name: 3})
    assert gate.callable(**{raw.name: 3, evidence.name: evidence_result}) == 3
    assert validator.values == [3]
