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
