import pytest

from autoops.operations import Operation, OperationStatus


def test_read_only_operation_executes_in_default_mode():
    operation = Operation("inspect", lambda: {"value": 42})

    result = operation.run()

    assert result.success is True
    assert result.status is OperationStatus.SUCCESS
    assert result.data == {"operation": "inspect", "value": 42}


def test_mutating_operation_defaults_to_dry_run_without_calling_action():
    calls = []
    operation = Operation("change-setting", lambda: calls.append(True), mutates_state=True)

    result = operation.run()

    assert result.success is True
    assert result.status is OperationStatus.DRY_RUN
    assert calls == []
    assert result.to_dict()["status"] == "dry-run"


def test_mutating_operation_requires_explicit_dry_run_false():
    calls = []

    def action():
        calls.append(True)
        return {"changed": True}

    result = Operation("change-setting", action, mutates_state=True).run(dry_run=False)

    assert result.status is OperationStatus.SUCCESS
    assert calls == [True]
    assert result.data["changed"] is True


def test_operation_rejects_non_boolean_mutation_flag():
    with pytest.raises(TypeError, match="mutates_state must be a boolean"):
        Operation("unsafe-definition", lambda: None, mutates_state=1)  # type: ignore[arg-type]


def test_operation_rejects_non_boolean_dry_run_before_action_executes():
    calls = []
    operation = Operation("change-setting", lambda: calls.append(True), mutates_state=True)

    for value in (0, 1, None, "false", "true"):
        with pytest.raises(TypeError, match="dry_run must be a boolean"):
            operation.run(dry_run=value)  # type: ignore[arg-type]

    assert calls == []


def test_operation_failure_is_normalized_without_leaking_exception_text():
    secret = "api-token-super-secret"

    def fail():
        raise RuntimeError(f"request failed with token {secret}")

    result = Operation("failing-check", fail).run()

    assert result.success is False
    assert result.status is OperationStatus.FAILED
    assert result.data["error_type"] == "RuntimeError"
    assert result.data["operation"] == "failing-check"
    assert secret not in result.message
    assert "request failed" not in result.message
    assert "suppressed" in result.message
    assert secret not in str(result.to_dict())


def test_operation_none_result_is_normalized_to_empty_data():
    result = Operation("no-data", lambda: None).run()

    assert result.success is True
    assert result.status is OperationStatus.SUCCESS
    assert result.data == {"operation": "no-data"}


def test_operation_invalid_result_type_is_normalized_failure():
    result = Operation("bad-result", lambda: ["unexpected", "list"]).run()

    assert result.success is False
    assert result.status is OperationStatus.FAILED
    assert result.message == "bad-result failed; operation returned an invalid result type."
    assert result.data == {"operation": "bad-result", "error_type": "InvalidResultType"}


def test_operation_cannot_override_reserved_operation_metadata():
    result = Operation("trusted-name", lambda: {"operation": "spoofed-name", "value": 42}).run()

    assert result.success is False
    assert result.status is OperationStatus.FAILED
    assert result.message == "trusted-name failed; operation returned reserved result metadata."
    assert result.data == {"operation": "trusted-name", "error_type": "ReservedResultKey"}


def test_operation_rejects_blank_name():
    for name in ("", "   ", "\t"):
        try:
            Operation(name, lambda: None)
        except ValueError as exc:
            assert str(exc) == "operation name must be a non-empty string"
        else:
            raise AssertionError("blank operation name should be rejected")


def test_operation_rejects_non_callable_action():
    try:
        Operation("invalid-action", None)  # type: ignore[arg-type]
    except TypeError as exc:
        assert str(exc) == "operation action must be callable"
    else:
        raise AssertionError("non-callable operation action should be rejected")
