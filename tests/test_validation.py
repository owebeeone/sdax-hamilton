"""Hamilton validation gates preserve semantics without exposing diagnostic payloads."""

import gc
import inspect
import logging
import weakref

import pytest
from hamilton import node
from hamilton.data_quality.base import DataValidationError, DataValidator, ValidationResult
from hamilton.function_modifiers import check_output_custom

from sdax_hamilton import Driver
from sdax_hamilton._hamilton_validation import correct_validation_gate
from sdax_hamilton._model import GeneratedRole


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


class MinimumValidator(DataValidator):
    def __init__(self, minimum: int) -> None:
        super().__init__("fail")
        self.minimum = minimum

    @classmethod
    def name(cls) -> str:
        return "minimum"

    def applies_to(self, datatype: type[type]) -> bool:
        return datatype is int

    def description(self) -> str:
        return "minimum"

    def validate(self, dataset):
        return ValidationResult(dataset >= self.minimum, "minimum result", {})


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


def leaves(error):
    if isinstance(error, BaseExceptionGroup):
        return [leaf for nested in error.exceptions for leaf in leaves(nested)]
    return [error]


@pytest.mark.asyncio
async def test_default_fail_validation_survives_disabled_output_checks_and_retries(
    module_factory,
):
    calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import check_output
from sdax_hamilton import execution

@execution(retries=2, initial_delay=0, retryable_exceptions=(Exception,))
@check_output(range=(0, 3), importance="fail")
def result() -> int:
    calls.append("result")
    return 5
""",
        calls=calls,
    )

    with pytest.raises(BaseExceptionGroup) as error:
        await Driver(module).prepare(["result"], check_outputs=False).execute()

    assert any(isinstance(leaf, DataValidationError) for leaf in leaves(error.value))
    assert calls == ["result"]


@pytest.mark.asyncio
async def test_default_warn_validation_returns_value_with_minimal_log(module_factory, caplog):
    module = module_factory(
        """
from hamilton.function_modifiers import check_output

@check_output(range=(0, 3), importance="warn")
def result() -> int:
    return 5
"""
    )

    with caplog.at_level(logging.WARNING):
        assert await Driver(module).prepare(["result"]).execute() == {"result": 5}

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "node=result" in rendered
    assert "validator=result_range_validator" in rendered
    assert "status=failed" in rendered and "level=warn" in rendered


@pytest.mark.asyncio
async def test_custom_fail_validation_omits_raw_diagnostics_in_full_driver(module_factory, caplog):
    secret = "SENTINEL-FULL-DRIVER-VALIDATION"
    validator = RecordingValidator(
        "secret validator",
        "fail",
        ValidationResult(False, secret, {"payload": secret}),
    )
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom

@check_output_custom(validator)
def result() -> str:
    return secret
""",
        secret=secret,
        validator=validator,
    )

    with caplog.at_level(logging.WARNING), pytest.raises(BaseExceptionGroup) as error:
        await Driver(module).prepare(["result"]).execute()

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    rendered += f"\n{error.value}"
    assert secret not in rendered
    assert "node=result" in rendered and "validator=result_recording" in rendered
    assert validator.values == [secret]


@pytest.mark.asyncio
async def test_custom_validator_error_identity_survives_full_driver(module_factory):
    failure = RuntimeError("user validator failure")
    validator = RecordingValidator("failure", "fail", failure)
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom

@check_output_custom(validator)
def result() -> int:
    return 1
""",
        validator=validator,
    )

    with pytest.raises(BaseExceptionGroup) as error:
        await Driver(module).prepare(["result"]).execute()

    assert failure in leaves(error.value)


@pytest.mark.asyncio
async def test_async_custom_validator_executes_through_full_driver(module_factory):
    validator = AsyncRecordingValidator(
        "async", "fail", ValidationResult(True, "accepted", {})
    )
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom

@check_output_custom(validator)
async def result() -> int:
    return 3
""",
        validator=validator,
    )

    assert await Driver(module).prepare(["result"]).execute() == {"result": 3}
    assert validator.values == [3]


@pytest.mark.asyncio
async def test_validation_target_applies_only_to_selected_parameterized_output(module_factory):
    calls = []
    validator = RecordingValidator(
        "validator", "fail", ValidationResult(False, "rejected", {})
    )
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom, parameterize, value

@check_output_custom(validator, target_="left")
@parameterize(left={"number": value(1)}, right={"number": value(2)})
def result(number: int) -> int:
    calls.append(number)
    return number
""",
        calls=calls,
        validator=validator,
    )
    driver = Driver(module)

    assert await driver.prepare(["right"]).execute() == {"right": 2}
    with pytest.raises(BaseExceptionGroup) as error:
        await driver.prepare(["left"]).execute()
    assert any(isinstance(leaf, DataValidationError) for leaf in leaves(error.value))
    assert calls == [2, 1]


@pytest.mark.asyncio
async def test_validation_target_tuple_keeps_each_generated_gate_isolated(module_factory):
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom, parameterize, value

@check_output_custom(validator, target_=("left", "right"))
@parameterize(
    left={"number": value(3)},
    right={"number": value(1)},
    unvalidated={"number": value(0)},
)
def result(number: int) -> int:
    return number
""",
        validator=MinimumValidator(2),
    )
    driver = Driver(module)

    for target in ("left", "right"):
        raw = f"{target}_raw"
        evidence = f"{target}_minimum"
        assert set(driver._nodes[evidence].inputs) == {raw}
        assert set(driver._nodes[target].inputs) == {raw, evidence}
        assert driver._nodes[raw].role is GeneratedRole.VALIDATION_RAW
        assert driver._nodes[evidence].role is GeneratedRole.VALIDATION_EVIDENCE
        assert driver._nodes[target].role is GeneratedRole.VALIDATION_GATE
    assert driver._nodes["unvalidated"].role is GeneratedRole.VALUE
    assert await driver.prepare(["left", "unvalidated"]).execute() == {
        "left": 3,
        "unvalidated": 0,
    }
    with pytest.raises(BaseExceptionGroup) as error:
        await driver.prepare(["right"]).execute()
    assert any(isinstance(leaf, DataValidationError) for leaf in leaves(error.value))


@pytest.mark.asyncio
async def test_validation_targeting_pipeline_helper_preserves_each_declared_owner(
    module_factory,
):
    events = []
    validator = RecordingValidator(
        "validator", "fail", ValidationResult(True, "accepted", {})
    )
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom, pipe_output, step
from sdax_hamilton import Acquisition, shutdown

def add(value: int) -> int:
    events.append(("add", value))
    return value + 1

@check_output_custom(validator, target_="result.with_add")
@pipe_output(step(add))
def result(value: int) -> int:
    events.append(("result", value))
    return value

@shutdown(of=add)
def close_add(state: Acquisition[int]) -> None:
    events.append(("close_add", state.value))

@shutdown(of=result, target_="result")
def close_result(state: Acquisition[int]) -> None:
    events.append(("close_result", state.value))
""",
        events=events,
        validator=validator,
    )
    driver = Driver(module)
    helper_raw = driver._nodes["result.with_add_raw"]
    outer_raw = driver._nodes["result.raw"]

    assert helper_raw.role is GeneratedRole.VALIDATION_RAW
    assert helper_raw.origin.endswith(".add")
    assert helper_raw.ownership_required
    assert helper_raw.release.__name__ == "close_add"
    assert outer_raw.origin.endswith(".result")
    assert outer_raw.ownership_required
    assert outer_raw.release.__name__ == "close_result"
    assert driver._nodes["result.with_add"].role is GeneratedRole.VALIDATION_GATE
    with pytest.raises(ValueError, match="Cannot replace validation"):
        driver.prepare(["result"], override_nodes=["result.with_add"])
    assert events == []

    plan = driver.prepare(["result"])
    with pytest.raises(ValueError, match="open"):
        await plan.execute(inputs={"value": 4})
    assert events == []
    async with plan.open(inputs={"value": 4}) as output:
        assert output == {"result": 5}
        assert events == [("result", 4), ("add", 4)]
    assert events.count(("close_add", 5)) == 1
    assert events.count(("close_result", 4)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("decorators", "gate", "owner"),
    [
        (
            '@extract_fields({"field": int})\n@check_output_custom(validator)',
            "resource",
            "resource_raw",
        ),
        (
            '@check_output_custom(validator)\n@extract_fields({"field": int})',
            "field",
            "resource",
        ),
    ],
)
async def test_validation_and_extract_fields_both_orders_preserve_gate_and_owner(
    module_factory, decorators, gate, owner
):
    events = []
    validator = RecordingValidator(
        "validator", "fail", ValidationResult(True, "accepted", {})
    )
    module = module_factory(
        f"""
from hamilton.function_modifiers import check_output_custom, extract_fields
from sdax_hamilton import Acquisition, shutdown

{decorators}
def resource() -> dict[str, int]:
    events.append("acquire")
    return {{"field": 3}}

@shutdown(of=resource)
def close(state: Acquisition[dict[str, int]]) -> None:
    events.append("release")
""",
        events=events,
        validator=validator,
    )
    driver = Driver(module)

    assert driver._nodes[gate].role is GeneratedRole.VALIDATION_GATE
    assert driver._nodes[owner].ownership_required
    assert driver._nodes[owner].release.__name__ == "close"
    with pytest.raises(ValueError, match="Cannot replace validation"):
        driver.prepare(["field"], override_nodes=[gate])
    with pytest.raises(ValueError, match="Cannot replace validation"):
        Driver(module, config={gate: 1}).prepare(["field"])
    assert events == []

    plan = driver.prepare(["field"], check_outputs=False)
    with pytest.raises(ValueError, match="open"):
        await plan.execute()
    assert events == []
    async with plan.open() as output:
        assert output == {"field": 3}
        assert events == ["acquire"]
    assert events == ["acquire", "release"]


@pytest.mark.parametrize("outer", ["default", "custom"])
def test_stacked_validation_decorators_are_rejected_as_upstream_invalid(module_factory, outer):
    decorators = (
        '@check_output(range=(0, 4), importance="fail")\n@check_output_custom(validator)'
        if outer == "default"
        else '@check_output_custom(validator)\n@check_output(range=(0, 4), importance="fail")'
    )
    module = module_factory(
        f"""
from hamilton.function_modifiers import check_output, check_output_custom

{decorators}
def result() -> int:
    return 1
""",
        validator=MinimumValidator(0),
    )

    with pytest.raises(ValueError, match="duplicate generated Hamilton node"):
        Driver(module)


def test_compiled_validation_roles_block_selection_replacement_and_raw_edges(module_factory):
    validator = RecordingValidator("validator", "fail", ValidationResult(True, "", {}))
    calls = []
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom

@check_output_custom(validator)
def result() -> int:
    return 1

def bypass(result_raw: int) -> int:
    calls.append("bypass")
    return result_raw

def independent() -> int:
    calls.append("independent")
    return 1
""",
        calls=calls,
        validator=validator,
    )
    driver = Driver(module)
    assert driver._nodes["result_raw"].role is GeneratedRole.VALIDATION_RAW
    assert driver._nodes["result_recording"].role is GeneratedRole.VALIDATION_EVIDENCE
    assert driver._nodes["result"].role is GeneratedRole.VALIDATION_GATE

    for internal in ("result_raw", "result_recording"):
        with pytest.raises(ValueError, match="internals cannot be selected"):
            driver.prepare([internal])
    for protected in ("result_raw", "result_recording", "result"):
        with pytest.raises(ValueError, match="Cannot replace validation"):
            driver.prepare(["result"], override_nodes=[protected])
        with pytest.raises(ValueError, match="Cannot replace validation"):
            Driver(module, config={protected: 1}).prepare(["result"])
    with pytest.raises(ValueError, match="internal edge"):
        driver.prepare(["bypass", "independent"])
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [None, "resource"])
async def test_validated_acquisition_public_shutdown_target_maps_to_raw_once(
    module_factory, target
):
    events = []
    validator = RecordingValidator("validator", "fail", ValidationResult(True, "", {}))
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom
from sdax_hamilton import Acquisition, shutdown

@check_output_custom(validator)
def resource() -> Handle:
    events.append("acquire")
    return Handle()

@shutdown(of=resource, target_=target)
def close(state: Acquisition[Handle]) -> None:
    assert state.value.live
    state.value.live = False
    events.append("release")
""",
        Handle=type("OwnedHandle", (), {"live": True}),
        events=events,
        target=target,
        validator=validator,
    )
    plan = Driver(module).prepare(["resource"])

    with pytest.raises(ValueError, match="open"):
        await plan.execute()
    assert events == []
    async with plan.open() as result:
        assert result["resource"].live
        assert events == ["acquire"]
    assert events == ["acquire", "release"]


@pytest.mark.asyncio
async def test_failed_validation_releases_compiled_raw_acquisition_once(module_factory):
    events = []
    warning = RecordingValidator(
        "warning", "warn", ValidationResult(False, "warning payload", {})
    )
    validator = RecordingValidator(
        "validator", "fail", ValidationResult(False, "rejected", {})
    )
    module = module_factory(
        """
from hamilton.function_modifiers import check_output_custom
from sdax_hamilton import Acquisition, shutdown

@check_output_custom(warning, validator)
def resource() -> Handle:
    events.append("acquire")
    return Handle()

@shutdown(of=resource)
def close(state: Acquisition[Handle]) -> None:
    state.value.live = False
    events.append("release")
""",
        Handle=type("RejectedHandle", (), {"live": True}),
        events=events,
        validator=validator,
        warning=warning,
    )

    with pytest.raises(BaseExceptionGroup):
        async with Driver(module).prepare(["resource"]).open():
            raise AssertionError("failed validation must not yield")
    assert events == ["acquire", "release"]
    assert len(warning.values) == 1 and warning.values == validator.values
