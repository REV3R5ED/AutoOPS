"""Safety-first contracts for AutoOPS operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class OperationStatus(str, Enum):
    """Portable status values for automation results."""

    SUCCESS = "success"
    DRY_RUN = "dry-run"
    FAILED = "failed"


@dataclass(frozen=True)
class OperationResult:
    """Serializable outcome returned by an AutoOPS operation."""

    success: bool
    status: OperationStatus
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


@dataclass(frozen=True)
class Operation:
    """A named operation with explicit mutation semantics.

    Mutating operations are never executed unless ``dry_run`` is exactly False.
    Callers should default to dry-run when exposing these operations through
    user-facing interfaces. Boolean safety flags are validated strictly so
    loosely typed programmatic callers cannot accidentally authorize mutation.
    Operation names reject control characters so audit and terminal output
    cannot be structurally altered by malformed automation definitions.
    """

    name: str
    action: Callable[[], dict[str, Any] | None]
    mutates_state: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("operation name must be a non-empty string")
        if any(ord(character) < 32 or ord(character) == 127 for character in self.name):
            raise ValueError("operation name must not contain control characters")
        if not callable(self.action):
            raise TypeError("operation action must be callable")
        if not isinstance(self.mutates_state, bool):
            raise TypeError("mutates_state must be a boolean")

    def run(self, *, dry_run: bool = True, verbose: bool = False) -> OperationResult:
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a boolean")
        if not isinstance(verbose, bool):
            raise TypeError("verbose must be a boolean")

        if self.mutates_state and dry_run:
            return OperationResult(
                success=True,
                status=OperationStatus.DRY_RUN,
                message=f"Dry run: {self.name} would execute; no changes were made.",
                data={"operation": self.name, "mutates_state": True},
            )

        try:
            data = self.action()
        except Exception as exc:  # Operation boundary intentionally normalizes failures.
            # Exception text can contain credentials, tokens, paths, command output,
            # or other sensitive runtime details. Keep the public result useful for
            # diagnostics without propagating the exception message to reports/logs.
            # An operator can opt into full exception detail with verbose=True; the
            # suppressed default keeps automated reports and audit logs safe.
            if verbose:
                detail = f"{type(exc).__name__}: {exc}"
                return OperationResult(
                    success=False,
                    status=OperationStatus.FAILED,
                    message=f"{self.name} failed: {detail}",
                    data={"operation": self.name, "error_type": type(exc).__name__, "error_detail": detail},
                )
            return OperationResult(
                success=False,
                status=OperationStatus.FAILED,
                message=f"{self.name} failed; sensitive exception details were suppressed.",
                data={"operation": self.name, "error_type": type(exc).__name__},
            )

        if data is None:
            data = {}
        elif not isinstance(data, dict):
            return OperationResult(
                success=False,
                status=OperationStatus.FAILED,
                message=f"{self.name} failed; operation returned an invalid result type.",
                data={"operation": self.name, "error_type": "InvalidResultType"},
            )
        elif "operation" in data:
            return OperationResult(
                success=False,
                status=OperationStatus.FAILED,
                message=f"{self.name} failed; operation returned reserved result metadata.",
                data={"operation": self.name, "error_type": "ReservedResultKey"},
            )

        return OperationResult(
            success=True,
            status=OperationStatus.SUCCESS,
            message=f"{self.name} completed successfully.",
            data={"operation": self.name, **data},
        )


def operation_from_check(
    name: str,
    check: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Operation:
    """Wrap a read-only check callable as a non-mutating :class:`Operation`.

    The check must return an object exposing ``to_dict()`` (all built-in
    AutoOPS checks do) so the operation result serializes cleanly for
    workflows, reports, and audit logging. The wrapped operation never
    mutates state, so it executes even under the default dry-run decision.
    """

    def action() -> dict[str, Any]:
        status = check(*args, **kwargs)
        to_dict = getattr(status, "to_dict", None)
        if not callable(to_dict):
            raise TypeError(f"check {name!r} did not return a serializable status object")
        payload = to_dict()
        if not isinstance(payload, dict):
            raise TypeError(f"check {name!r} did not return a serializable status object")
        return payload

    return Operation(name, action, mutates_state=False)
