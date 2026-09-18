"""Read-only health assessment for locally produced operational artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from autoops.checks import file_freshness


@dataclass(frozen=True)
class ArtifactStatus:
    """Serializable health result for an expected local artifact."""

    path: str
    size_bytes: int | None
    modified_at: str | None
    age_seconds: float | None
    max_age_seconds: float
    min_size_bytes: int
    state: str

    def to_dict(self) -> dict[str, str | int | float | None]:
        return asdict(self)


@dataclass(frozen=True)
class ArtifactExpectation:
    """Expected health constraints for one local artifact."""

    path: str
    max_age_seconds: float
    min_size_bytes: int = 0


@dataclass(frozen=True)
class ArtifactBatchStatus:
    """Deterministic summary for a set of expected artifacts."""

    total: int
    healthy: int
    unhealthy: int
    states: dict[str, int]
    artifacts: tuple[ArtifactStatus, ...]

    @property
    def ok(self) -> bool:
        return self.unhealthy == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "total": self.total,
            "healthy": self.healthy,
            "unhealthy": self.unhealthy,
            "ok": self.ok,
            "states": dict(self.states),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


def artifact_health(
    path: str,
    max_age_seconds: float,
    *,
    min_size_bytes: int = 0,
    now: datetime | None = None,
) -> ArtifactStatus:
    """Assess whether a local artifact is recent enough and large enough.

    The check is read-only and intended for backups, exports, reports, and logs
    whose mere existence is not sufficient evidence of health. Timestamp
    anomalies and staleness take precedence over size so operators see the most
    fundamental production problem first.
    """
    if not isinstance(min_size_bytes, int) or isinstance(min_size_bytes, bool) or min_size_bytes < 0:
        raise ValueError("min_size_bytes must be a non-negative integer")

    freshness = file_freshness(path, max_age_seconds, now=now)
    if freshness.state in {"future", "stale"}:
        state = freshness.state
    elif freshness.size_bytes < min_size_bytes:
        state = "undersized"
    else:
        state = "ok"

    return ArtifactStatus(
        path=freshness.path,
        size_bytes=freshness.size_bytes,
        modified_at=freshness.modified_at,
        age_seconds=freshness.age_seconds,
        max_age_seconds=freshness.max_age_seconds,
        min_size_bytes=min_size_bytes,
        state=state,
    )


def _missing_status(expectation: ArtifactExpectation) -> ArtifactStatus:
    """Represent an expected artifact that does not exist without inventing metadata."""
    return ArtifactStatus(
        path=str(Path(expectation.path).resolve()),
        size_bytes=None,
        modified_at=None,
        age_seconds=None,
        max_age_seconds=expectation.max_age_seconds,
        min_size_bytes=expectation.min_size_bytes,
        state="missing",
    )


def assess_artifacts(
    expectations: Iterable[ArtifactExpectation],
    *,
    now: datetime | None = None,
) -> ArtifactBatchStatus:
    """Assess several local artifacts and return an aggregate health summary.

    At least one unique expectation is required so an accidentally empty or
    duplicated caller cannot produce misleading operational totals. The supplied
    order is preserved so reports remain predictable. A missing expected path is
    reported as an unhealthy ``missing`` state so one absent backup or export does
    not hide the health of the remaining batch. Other filesystem errors are still
    surfaced explicitly rather than being converted into ambiguous health results.
    """
    items = tuple(expectations)
    if not items:
        raise ValueError("at least one artifact expectation is required")

    resolved_paths = [Path(item.path).resolve() for item in items]
    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError("artifact expectation paths must be unique")

    statuses_list: list[ArtifactStatus] = []
    for item in items:
        try:
            status = artifact_health(
                item.path,
                item.max_age_seconds,
                min_size_bytes=item.min_size_bytes,
                now=now,
            )
        except FileNotFoundError:
            status = _missing_status(item)
        statuses_list.append(status)

    statuses = tuple(statuses_list)
    states = ("ok", "missing", "stale", "future", "undersized")
    counts = {state: sum(status.state == state for status in statuses) for state in states}
    healthy = counts["ok"]
    return ArtifactBatchStatus(
        total=len(statuses),
        healthy=healthy,
        unhealthy=len(statuses) - healthy,
        states=counts,
        artifacts=statuses,
    )
