from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from autoops.checks import disk_status, environment_status, file_freshness


def test_disk_status_reports_consistent_capacity(tmp_path: Path) -> None:
    status = disk_status(str(tmp_path))

    assert status.path == str(tmp_path.resolve())
    assert status.total_bytes > 0
    assert status.used_bytes >= 0
    assert status.free_bytes >= 0
    assert status.used_bytes + status.free_bytes <= status.total_bytes
    assert 0 <= status.used_percent <= 100


def test_disk_status_rejects_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        disk_status(str(missing))


def test_environment_status_is_serializable_and_populated() -> None:
    status = environment_status()
    payload = status.to_dict()

    assert payload["hostname"]
    assert payload["platform"]
    assert payload["platform_release"]
    assert payload["architecture"]
    assert payload["python_version"]
    assert payload["cpu_count"] is None or payload["cpu_count"] >= 1


def test_file_freshness_reports_ok_and_stale_states(tmp_path: Path) -> None:
    target = tmp_path / "backup.json"
    target.write_text("{}", encoding="utf-8")
    now = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
    modified = now - timedelta(minutes=10)
    os.utime(target, (modified.timestamp(), modified.timestamp()))

    fresh = file_freshness(str(target), 900, now=now)
    stale = file_freshness(str(target), 300, now=now)

    assert fresh.path == str(target.resolve())
    assert fresh.size_bytes == 2
    assert fresh.age_seconds == 600.0
    assert fresh.state == "ok"
    assert stale.state == "stale"
    assert stale.max_age_seconds == 300.0


def test_file_freshness_reports_future_timestamp_as_anomaly(tmp_path: Path) -> None:
    target = tmp_path / "backup.json"
    target.write_text("{}", encoding="utf-8")
    now = datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc)
    modified = now + timedelta(minutes=5)
    os.utime(target, (modified.timestamp(), modified.timestamp()))

    status = file_freshness(str(target), 900, now=now)

    assert status.state == "future"
    assert status.age_seconds == 0.0
    assert status.modified_at == modified.isoformat().replace("+00:00", "Z")


def test_file_freshness_rejects_missing_and_non_file_paths(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Path does not exist"):
        file_freshness(str(tmp_path / "missing"), 60)
    with pytest.raises(ValueError, match="not a regular file"):
        file_freshness(str(tmp_path), 60)


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), True, "60"])
def test_file_freshness_rejects_invalid_max_age(tmp_path: Path, value) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("ok", encoding="utf-8")
    with pytest.raises(ValueError, match="finite non-negative number"):
        file_freshness(str(target), value)


def test_file_freshness_rejects_naive_reference_time(tmp_path: Path) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("ok", encoding="utf-8")
    with pytest.raises(ValueError, match="timezone-aware"):
        file_freshness(str(target), 60, now=datetime(2026, 9, 16, 20, 0))
