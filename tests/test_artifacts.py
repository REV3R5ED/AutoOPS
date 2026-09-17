from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from autoops.artifacts import artifact_health


def _artifact(tmp_path: Path, content: str, modified: datetime) -> Path:
    target = tmp_path / "backup.json"
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
