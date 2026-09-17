"""Read-only health assessment for locally produced operational artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from autoops.checks import file_freshness


@dataclass(frozen=True)
class ArtifactStatus:
    """Serializable health result for an expected local artifact."""

    path: str
    size_bytes: int
    modified_at: str
    age_seconds: float
    max_age_seconds: float
    min_size_bytes: int
    state: str

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


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
