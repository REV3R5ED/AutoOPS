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
        with pytest.raises(ValueError, match="operation name must be a non-empty string"):
            Operation(name, lambda: None)


def test_operation_rejects_control_characters_in_name():
    for name in ("check\nforged", "check\rforged", "check\x00forged", "check\x7fforged"):
        with pytest.raises(ValueError, match="operation name must not contain control characters"):
            Operation(name, lambda: None)


def test_operation_rejects_non_callable_action():
    with pytest.raises(TypeError, match="operation action must be callable"):
        Operation("invalid-action", None)  # type: ignore[arg-type]


def test_verbose_run_reveals_exception_detail() -> None:
    secret = "api-token-super-secret"

    def fail():
        raise RuntimeError(f"request failed with token {secret}")

    result = Operation("failing-check", fail).run(verbose=True)
    assert result.success is False
    assert result.status is OperationStatus.FAILED
    assert secret in result.message
    assert result.data["error_type"] == "RuntimeError"
    assert result.data["error_detail"] == f"RuntimeError: request failed with token {secret}"


def test_verbose_defaults_to_suppressed() -> None:
    def fail():
        raise RuntimeError("request failed with token hunter2")

    result = Operation("failing-check", fail).run()
    assert result.success is False
    assert "suppressed" in result.message
    assert "hunter2" not in result.message
    assert "error_detail" not in result.data


def test_run_rejects_non_boolean_verbose() -> None:
    operation = Operation("inspect", lambda: {"value": 1})
    with pytest.raises(TypeError, match="verbose must be a boolean"):
        operation.run(verbose=1)


def test_verbose_does_not_affect_dry_run() -> None:
    calls = []
    operation = Operation("change", lambda: calls.append(True) or {"changed": True}, mutates_state=True)
    result = operation.run(verbose=True)
    assert result.status is OperationStatus.DRY_RUN
    assert calls == []


def test_operation_from_check_wraps_status_object() -> None:
    from autoops.checks import disk_status
    from autoops.operations import operation_from_check

    operation = operation_from_check("disk-check", disk_status, ".")
    assert operation.name == "disk-check"
    assert operation.mutates_state is False
    result = operation.run()
    assert result.success is True
    assert result.data["operation"] == "disk-check"
    assert "used_percent" in result.data


def test_operation_from_check_rejects_non_serializable_check() -> None:
    from autoops.operations import operation_from_check

    operation = operation_from_check("bad-check", lambda: 42)
    result = operation.run()
    assert result.success is False
    assert result.status is OperationStatus.FAILED
