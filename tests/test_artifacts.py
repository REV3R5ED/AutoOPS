from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from autoops.artifacts import ArtifactExpectation, artifact_health, assess_artifacts


def _artifact(tmp_path: Path, content: str, modified: datetime, name: str = "backup.json") -> Path:
    target = tmp_path / name
    target.write_text(content, encoding="utf-8")
    os.utime(target, (modified.timestamp(), modified.timestamp()))
    return target


def test_artifact_health_reports_ok_when_recent_and_large_enough(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    target = _artifact(tmp_path, "{\"ok\": true}", now - timedelta(minutes=2))

    status = artifact_health(str(target), 300, min_size_bytes=4, now=now)

    assert status.state == "ok"
    assert status.size_bytes >= 4
    assert status.min_size_bytes == 4
    assert status.to_dict()["path"] == str(target.resolve())


def test_artifact_health_detects_recent_but_undersized_output(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    target = _artifact(tmp_path, "", now - timedelta(seconds=30))

    status = artifact_health(str(target), 300, min_size_bytes=1, now=now)

    assert status.state == "undersized"
    assert status.size_bytes == 0


def test_artifact_health_prioritizes_stale_and_future_anomalies(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    stale = _artifact(tmp_path, "", now - timedelta(hours=2))
    assert artifact_health(str(stale), 300, min_size_bytes=100, now=now).state == "stale"

    future_time = now + timedelta(minutes=5)
    os.utime(stale, (future_time.timestamp(), future_time.timestamp()))
    assert artifact_health(str(stale), 300, min_size_bytes=100, now=now).state == "future"


@pytest.mark.parametrize("value", [-1, 1.5, True, "1"])
def test_artifact_health_rejects_invalid_minimum_size(tmp_path: Path, value) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("ok", encoding="utf-8")

    with pytest.raises(ValueError, match="non-negative integer"):
        artifact_health(str(target), 60, min_size_bytes=value)


def test_assess_artifacts_summarizes_mixed_health_and_preserves_order(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    healthy = _artifact(tmp_path, "backup-data", now - timedelta(minutes=1), "backup.tar")
    stale = _artifact(tmp_path, "report", now - timedelta(hours=2), "report.json")
    small = _artifact(tmp_path, "x", now - timedelta(seconds=20), "export.csv")

    result = assess_artifacts(
        [
            ArtifactExpectation(str(healthy), 300, 4),
            ArtifactExpectation(str(stale), 300, 1),
            ArtifactExpectation(str(small), 300, 10),
        ],
        now=now,
    )

    assert result.total == 3
    assert result.healthy == 1
    assert result.unhealthy == 2
    assert result.ok is False
    assert result.states == {"ok": 1, "missing": 0, "stale": 1, "future": 0, "undersized": 1}
    assert [item.state for item in result.artifacts] == ["ok", "stale", "undersized"]
    assert result.to_dict()["ok"] is False


def test_assess_artifacts_reports_missing_and_continues_batch(tmp_path: Path) -> None:
    now = datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc)
    missing = tmp_path / "missing-backup.tar"
    healthy = _artifact(tmp_path, "report-data", now - timedelta(seconds=20), "report.json")

    result = assess_artifacts(
        [ArtifactExpectation(str(missing), 300, 10), ArtifactExpectation(str(healthy), 300, 1)],
        now=now,
    )

    assert result.total == 2
    assert result.healthy == 1
    assert result.unhealthy == 1
    assert result.states["missing"] == 1
    assert [item.state for item in result.artifacts] == ["missing", "ok"]
    assert result.artifacts[0].size_bytes is None
    assert result.artifacts[0].modified_at is None
    assert result.artifacts[0].age_seconds is None
    assert result.artifacts[0].path == str(missing.resolve())


def test_artifact_health_still_raises_for_missing_single_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        artifact_health(str(tmp_path / "absent.txt"), 60)


def test_assess_artifacts_rejects_empty_expectations() -> None:
    with pytest.raises(ValueError, match="at least one artifact expectation"):
        assess_artifacts([])


def test_assess_artifacts_rejects_duplicate_resolved_paths(tmp_path: Path) -> None:
    target = tmp_path / "backup.tar"
    duplicate_spelling = tmp_path / "." / "backup.tar"

    with pytest.raises(ValueError, match="paths must be unique"):
        assess_artifacts([
            ArtifactExpectation(str(target), 300),
            ArtifactExpectation(str(duplicate_spelling), 600),
        ])
