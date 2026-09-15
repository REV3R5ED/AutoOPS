from pathlib import Path

import pytest

from autoops.checks import disk_status


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
