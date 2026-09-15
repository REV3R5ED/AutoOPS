from datetime import datetime, timezone
import io
import json

import pytest

from autoops.logging import build_audit_event, redact, write_json_event
from autoops.operations import OperationResult, OperationStatus


def _result(data=None):
    return OperationResult(
        success=True,
        status=OperationStatus.SUCCESS,
        message="inspect completed successfully.",
        data=data or {"operation": "inspect", "value": 42},
    )


def test_build_audit_event_has_stable_utc_shape() -> None:
    event = build_audit_event(
        _result(),
        timestamp=datetime(2026, 9, 15, 12, 30, tzinfo=timezone.utc),
    )

    assert event == {
        "timestamp": "2026-09-15T12:30:00Z",
        "event": "operation_result",
        "success": True,
        "status": "success",
        "message": "inspect completed successfully.",
        "data": {"operation": "inspect", "value": 42},
    }


def test_redact_removes_nested_secret_fields_without_mutating_input() -> None:
    original = {
        "operation": "inspect",
        "api_token": "do-not-log",
        "nested": {"password": "hidden", "safe": "visible"},
        "items": [{"credential-id": "private"}],
    }

    redacted = redact(original)

    assert redacted["api_token"] == "[REDACTED]"
    assert redacted["nested"] == {"password": "[REDACTED]", "safe": "visible"}
    assert redacted["items"][0]["credential-id"] == "[REDACTED]"
    assert original["api_token"] == "do-not-log"


def test_write_json_event_emits_one_parseable_json_line() -> None:
    stream = io.StringIO()
    write_json_event(
        _result(),
        stream,
        timestamp=datetime(2026, 9, 15, 12, 30, tzinfo=timezone.utc),
    )

    lines = stream.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["data"]["operation"] == "inspect"


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_audit_event(_result(), timestamp=datetime(2026, 9, 15, 12, 30))
