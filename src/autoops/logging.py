"""Structured, redaction-aware audit logging for AutoOPS results."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any, TextIO

from autoops.operations import OperationResult

_SENSITIVE_MARKERS = ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")
_REDACTED = "[REDACTED]"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_MARKERS)


def redact(value: Any) -> Any:
    """Return a JSON-friendly copy with common secret-bearing fields redacted."""
    if isinstance(value, dict):
        return {
            str(key): _REDACTED if _is_sensitive_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def build_audit_event(
    result: OperationResult,
    *,
    timestamp: datetime | None = None,
) -> dict[str, Any]:
    """Build a stable structured event from an operation result."""
    occurred_at = timestamp or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")

    return {
        "timestamp": occurred_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": "operation_result",
        "success": result.success,
        "status": result.status.value,
        "message": result.message,
        "data": redact(result.data),
    }


def write_json_event(
    result: OperationResult,
    stream: TextIO,
    *,
    timestamp: datetime | None = None,
) -> None:
    """Write one newline-delimited JSON audit event to a text stream."""
    event = build_audit_event(result, timestamp=timestamp)
    stream.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
