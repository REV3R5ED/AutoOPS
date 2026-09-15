"""Safety-first contracts for AutoOPS operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable


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

    Mutating operations are never executed unless ``dry_run`` is False.
    Callers should default to dry-run when exposing these operations through
    user-facing interfaces.
    """

    name: str
    action: Callable[[], dict[str, Any] | None]
    mutates_state: bool = False

    def run(self, *, dry_run: bool = True) -> OperationResult:
        if self.mutates_state and dry_run:
            return OperationResult(
                success=True,
                status=OperationStatus.DRY_RUN,
                message=f"Dry run: {self.name} would execute; no changes were made.",
                data={"operation": self.name, "mutates_state": True},
            )

        try:
            data = self.action() or {}
        except Exception as exc:  # Operation boundary intentionally normalizes failures.
            return OperationResult(
                success=False,
                status=OperationStatus.FAILED,
                message=f"{self.name} failed: {exc}",
                data={"operation": self.name, "error_type": type(exc).__name__},
            )

        return OperationResult(
            success=True,
            status=OperationStatus.SUCCESS,
            message=f"{self.name} completed successfully.",
            data={"operation": self.name, **data},
        )
