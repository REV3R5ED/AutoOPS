"""Composable, safety-preserving workflows for AutoOPS operations."""

from __future__ import annotations

from dataclasses import dataclass

from autoops.operations import Operation, OperationResult


@dataclass(frozen=True)
class WorkflowResult:
    """Outcome of an ordered workflow execution."""

    name: str
    success: bool
    results: tuple[OperationResult, ...]
    stopped_early: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "success": self.success,
            "stopped_early": self.stopped_early,
            "results": [result.to_dict() for result in self.results],
        }


@dataclass(frozen=True)
class Workflow:
    """Run operations in order while preserving each operation's safety contract.

    Workflows fail fast by default so later steps do not run after a failure.
    The workflow-level ``dry_run`` value is passed to every operation; therefore
    mutating operations remain dry-run unless execution is explicitly requested.
    Boolean control flags are validated strictly so loosely typed callers cannot
    silently change fail-fast or dry-run semantics. Malformed workflow definitions
    are rejected at construction time so they cannot produce ambiguous audit
    identities or fail partway through execution.
    """

    name: str
    operations: tuple[Operation, ...]
    fail_fast: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("workflow name must be a non-empty string")
        if not self.operations:
            raise ValueError("workflow must contain at least one operation")
        if any(not isinstance(operation, Operation) for operation in self.operations):
            raise TypeError("workflow operations must contain only Operation instances")
        if not isinstance(self.fail_fast, bool):
            raise TypeError("fail_fast must be a boolean")

    def run(self, *, dry_run: bool = True) -> WorkflowResult:
        if not isinstance(dry_run, bool):
            raise TypeError("dry_run must be a boolean")

        results: list[OperationResult] = []
        stopped_early = False

        for index, operation in enumerate(self.operations):
            result = operation.run(dry_run=dry_run)
            results.append(result)
            if self.fail_fast and not result.success:
                stopped_early = index < len(self.operations) - 1
                break

        return WorkflowResult(
            name=self.name,
            success=all(result.success for result in results),
            results=tuple(results),
            stopped_early=stopped_early,
        )
