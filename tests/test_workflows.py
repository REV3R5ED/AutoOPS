import pytest

from autoops.operations import Operation, OperationStatus
from autoops.workflows import Workflow


def test_workflow_rejects_blank_name():
    with pytest.raises(ValueError, match="non-empty string"):
        Workflow("   ", (Operation("check", lambda: None),))


def test_workflow_rejects_non_string_name():
    with pytest.raises(ValueError, match="non-empty string"):
        Workflow(None, (Operation("check", lambda: None),))


def test_workflow_rejects_empty_operation_sequence():
    with pytest.raises(ValueError, match="at least one operation"):
        Workflow("empty", ())


def test_workflow_rejects_non_operation_members():
    with pytest.raises(TypeError, match="only Operation instances"):
        Workflow("invalid", (Operation("check", lambda: None), "not-an-operation"))


def test_workflow_rejects_non_boolean_fail_fast():
    for value in (0, 1, None, "false", "true"):
        with pytest.raises(TypeError, match="fail_fast must be a boolean"):
            Workflow("invalid-control", (Operation("check", lambda: None),), fail_fast=value)  # type: ignore[arg-type]


def test_workflow_rejects_non_boolean_dry_run_before_any_operation_executes():
    calls = []
    workflow = Workflow("safe-control", (Operation("check", lambda: calls.append(True)),))

    for value in (0, 1, None, "false", "true"):
        with pytest.raises(TypeError, match="dry_run must be a boolean"):
            workflow.run(dry_run=value)  # type: ignore[arg-type]

    assert calls == []


def test_workflow_runs_operations_in_order():
    calls = []
    workflow = Workflow(
        "inspect-system",
        (
            Operation("first", lambda: calls.append("first")),
            Operation("second", lambda: calls.append("second")),
        ),
    )

    result = workflow.run()

    assert result.success is True
    assert calls == ["first", "second"]
    assert [item.data["operation"] for item in result.results] == ["first", "second"]


def test_workflow_preserves_default_dry_run_for_mutating_steps():
    calls = []
    workflow = Workflow(
        "safe-maintenance",
        (Operation("change", lambda: calls.append("changed"), mutates_state=True),),
    )

    result = workflow.run()

    assert calls == []
    assert result.success is True
    assert result.results[0].status is OperationStatus.DRY_RUN


def test_workflow_requires_explicit_execution_for_mutating_steps():
    calls = []
    workflow = Workflow(
        "approved-maintenance",
        (Operation("change", lambda: calls.append("changed"), mutates_state=True),),
    )

    result = workflow.run(dry_run=False)

    assert calls == ["changed"]
    assert result.results[0].status is OperationStatus.SUCCESS


def test_workflow_fails_fast_and_skips_later_steps():
    calls = []

    def fail():
        calls.append("fail")
        raise RuntimeError("unhealthy")

    workflow = Workflow(
        "guarded",
        (
            Operation("precheck", lambda: calls.append("precheck")),
            Operation("failure", fail),
            Operation("later", lambda: calls.append("later")),
        ),
    )

    result = workflow.run()

    assert result.success is False
    assert result.stopped_early is True
    assert calls == ["precheck", "fail"]
    assert len(result.results) == 2
    assert result.to_dict()["results"][1]["status"] == "failed"


def test_workflow_can_collect_failures_when_fail_fast_disabled():
    calls = []

    def fail():
        calls.append("fail")
        raise ValueError("bad check")

    workflow = Workflow(
        "diagnostics",
        (
            Operation("failure", fail),
            Operation("later", lambda: calls.append("later")),
        ),
        fail_fast=False,
    )

    result = workflow.run()

    assert result.success is False
    assert result.stopped_early is False
    assert calls == ["fail", "later"]
    assert len(result.results) == 2
