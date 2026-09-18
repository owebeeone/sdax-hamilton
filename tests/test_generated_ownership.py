"""Generated validation roles and borrowed ownership remain non-bypassable."""

from typing import Any

import pytest
from hamilton.data_quality.base import DataValidationError, ValidationResult

from sdax_hamilton._model import GeneratedRole, InputSpec, NodeSpec
from sdax_hamilton.declarations import Policy
from sdax_hamilton.plan import PreparedPlan


class Handle:
    def __init__(self) -> None:
        self.live = True


def node(name, output_type, fn, inputs=(), **kwargs):
    return NodeSpec(name, fn, output_type, dict(inputs), **kwargs)


def validation_nodes(calls):
    raw = node(
        "result_raw",
        int,
        lambda: calls.append("raw") or 1,
        role=GeneratedRole.VALIDATION_RAW,
    )
    evidence = node(
        "result_validator",
        ValidationResult,
        lambda result_raw: ValidationResult(True, "accepted", {}),
        (("result_raw", InputSpec(int)),),
        role=GeneratedRole.VALIDATION_EVIDENCE,
    )
    gate = node(
        "result",
        int,
        lambda result_raw, result_validator: result_raw,
        (
            ("result_raw", InputSpec(int)),
            ("result_validator", InputSpec(ValidationResult)),
        ),
        role=GeneratedRole.VALIDATION_GATE,
    )
    return {entry.name: entry for entry in (raw, evidence, gate)}


@pytest.mark.asyncio
async def test_declared_default_is_passed_with_application_object_identity():
    payload = object()
    seen = []

    def result(value=payload) -> int:
        seen.append(value)
        return 1

    nodes = {"result": node("result", int, result, (("value", InputSpec(object, payload)),))}

    assert await PreparedPlan(nodes, ["result"]).execute() == {"result": 1}
    assert seen == [payload]


@pytest.mark.asyncio
async def test_captured_optional_source_default_is_injected_into_generated_callable():
    payload = object()
    seen = []
    nodes = {
        "result": node(
            "result",
            int,
            lambda rewritten_source: seen.append(rewritten_source) or 1,
            (("rewritten_source", InputSpec(object, payload)),),
        )
    }

    assert await PreparedPlan(nodes, ["result"]).execute() == {"result": 1}
    assert seen == [payload]


@pytest.mark.asyncio
async def test_generated_validation_helper_edges_execute():
    calls = []

    assert await PreparedPlan(validation_nodes(calls), ["result"]).execute() == {"result": 1}
    assert calls == ["raw"]


@pytest.mark.parametrize("output", ["result_raw", "result_validator"])
def test_validation_internals_cannot_be_public_outputs(output):
    with pytest.raises(ValueError, match="internals cannot be selected"):
        PreparedPlan(validation_nodes([]), [output])


@pytest.mark.parametrize("name", ["result_raw", "result_validator", "result"])
@pytest.mark.parametrize("replacement", ["config", "override"])
def test_validation_roles_cannot_be_replaced(name, replacement):
    nodes = validation_nodes([])
    kwargs = {replacement: None}
    if replacement == "config":
        kwargs = {"config": {name: 1}}
    else:
        kwargs = {"override_nodes": [name]}

    with pytest.raises(ValueError, match="Cannot replace validation"):
        PreparedPlan(nodes, ["result"], **kwargs)


def test_validation_replacement_rejected_before_independent_effect():
    calls = []
    nodes = validation_nodes(calls)
    nodes["independent"] = node(
        "independent", int, lambda: calls.append("independent") or 1
    )

    with pytest.raises(ValueError, match="Cannot replace validation"):
        PreparedPlan(nodes, ["result", "independent"], config={"result": 1})
    assert calls == []


def test_user_declared_raw_consumer_is_rejected_before_effects():
    calls = []
    nodes = validation_nodes(calls)
    nodes["bypass"] = node(
        "bypass",
        int,
        lambda result_raw: calls.append("bypass") or result_raw,
        (("result_raw", InputSpec(int)),),
    )
    nodes["independent"] = node(
        "independent", int, lambda: calls.append("independent") or 1
    )

    with pytest.raises(ValueError, match="internal edge"):
        PreparedPlan(nodes, ["bypass", "independent"])
    assert calls == []


def borrowed_nodes(events, *, owner_policy=Policy()):
    state = {}

    def acquire():
        handle = Handle()
        state["handle"] = handle
        events.append("acquire")
        return handle

    def release(acquisition):
        handle = acquisition.value
        assert handle.live
        handle.live = False
        events.append("release")

    def alias():
        handle = state["handle"]
        assert handle.live
        events.append("alias")
        return handle

    owner = node(
        "owner",
        Handle,
        acquire,
        release=release,
        policy=owner_policy,
        ownership_required=True,
    )
    borrowed = node("borrowed", Handle, alias, borrow_from=frozenset(("owner",)))
    return {"owner": owner, "borrowed": borrowed}, state


@pytest.mark.asyncio
async def test_borrowed_output_requires_open_and_retains_owner():
    events = []
    nodes, state = borrowed_nodes(events)
    plan = PreparedPlan(nodes, ["borrowed"])

    with pytest.raises(ValueError, match="open"):
        await plan.execute()
    assert events == []

    async with plan.open() as result:
        assert result["borrowed"] is state["handle"]
        assert result["borrowed"].live
        assert events == ["acquire", "alias"]
    assert events == ["acquire", "alias", "release"]
    assert not state["handle"].live


@pytest.mark.parametrize("replacement", ["config", "override"])
def test_borrowed_alias_cannot_be_replaced(replacement):
    nodes, _ = borrowed_nodes([])
    kwargs = (
        {"config": {"borrowed": Handle()}}
        if replacement == "config"
        else {"override_nodes": ["borrowed"]}
    )

    with pytest.raises(ValueError, match="borrowed"):
        PreparedPlan(nodes, ["borrowed"], **kwargs)


@pytest.mark.parametrize(
    "borrow_from",
    [frozenset(("missing",)), frozenset(("ordinary",)), frozenset(("borrowed",))],
)
def test_borrowed_owner_must_be_a_distinct_acquisition(borrow_from):
    nodes = {
        "ordinary": node("ordinary", int, lambda: 1),
        "borrowed": node("borrowed", int, lambda: 1, borrow_from=borrow_from),
    }

    with pytest.raises(ValueError, match="borrowed owner|not an acquisition"):
        PreparedPlan(nodes, ["borrowed"])


def test_borrowed_acquisition_retry_is_rejected():
    nodes, _ = borrowed_nodes([], owner_policy=Policy(retries=1))

    with pytest.raises(ValueError, match="Acquisition retries"):
        PreparedPlan(nodes, ["borrowed"])


@pytest.mark.asyncio
async def test_validation_failure_releases_raw_acquisition_once_with_checks_disabled():
    events = []

    def acquire():
        events.append("acquire")
        return Handle()

    def release(acquisition):
        events.append("release")
        acquisition.value.live = False

    def reject(result_raw):
        return ValidationResult(False, "payload must stay private", {})

    def gate(result_raw, result_validator):
        events.append("gate")
        if not result_validator.passes:
            raise DataValidationError(["minimal failure"])
        return result_raw

    nodes = {
        "result_raw": node(
            "result_raw",
            Handle,
            acquire,
            release=release,
            ownership_required=True,
            role=GeneratedRole.VALIDATION_RAW,
        ),
        "result_validator": node(
            "result_validator",
            ValidationResult,
            reject,
            (("result_raw", InputSpec(Handle)),),
            role=GeneratedRole.VALIDATION_EVIDENCE,
        ),
        "result": node(
            "result",
            Handle,
            gate,
            (
                ("result_raw", InputSpec(Handle)),
                ("result_validator", InputSpec(ValidationResult)),
            ),
            role=GeneratedRole.VALIDATION_GATE,
            borrow_from=frozenset(("result_raw",)),
        ),
    }

    plan = PreparedPlan(nodes, ["result"], check_outputs=False)
    with pytest.raises(BaseExceptionGroup):
        async with plan.open():
            raise AssertionError("failed validation must not yield")
    assert events == ["acquire", "gate", "release"]


@pytest.mark.asyncio
async def test_pre_call_binding_failure_releases_empty_acquisition_once():
    states = []
    calls = []
    nodes = {
        "source": node("source", Any, lambda: "wrong"),
        "result_raw": node(
            "result_raw",
            Handle,
            lambda source: calls.append("acquire") or Handle(),
            (("source", InputSpec(object, requirements=(int,))),),
            release=lambda acquisition: states.append(acquisition),
            ownership_required=True,
            role=GeneratedRole.VALIDATION_RAW,
        ),
        "result_validator": node(
            "result_validator",
            ValidationResult,
            lambda result_raw: ValidationResult(True, "", {}),
            (("result_raw", InputSpec(Handle)),),
            role=GeneratedRole.VALIDATION_EVIDENCE,
        ),
        "result": node(
            "result",
            Handle,
            lambda result_raw, result_validator: result_raw,
            (
                ("result_raw", InputSpec(Handle)),
                ("result_validator", InputSpec(ValidationResult)),
            ),
            role=GeneratedRole.VALIDATION_GATE,
            borrow_from=frozenset(("result_raw",)),
        ),
    }

    with pytest.raises(BaseExceptionGroup):
        async with PreparedPlan(nodes, ["result"]).open():
            raise AssertionError("binding failure must not yield")
    assert calls == []
    assert len(states) == 1 and not states[0].has_value
