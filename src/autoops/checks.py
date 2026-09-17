"""Read-only system health checks used by AutoOPS."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import os
import platform
import shutil
import socket
import sys
from pathlib import Path


@dataclass(frozen=True)
class DiskStatus:
    """A serializable snapshot of filesystem capacity."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentStatus:
    """A read-only, cross-platform snapshot useful for operational preflight checks."""

    hostname: str
    platform: str
    platform_release: str
    architecture: str
    python_version: str
    cpu_count: int | None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


@dataclass(frozen=True)
class FileFreshnessStatus:
    """A serializable snapshot describing how recently a file was modified."""

    path: str
    size_bytes: int
    modified_at: str
    age_seconds: float
    max_age_seconds: float
    state: str

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


def disk_status(path: str = ".") -> DiskStatus:
    """Return a read-only disk usage snapshot for *path*.

    Raises FileNotFoundError when the requested path does not exist.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")

    usage = shutil.disk_usage(target)
    used_percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
    return DiskStatus(
        path=str(target.resolve()),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        used_percent=round(used_percent, 2),
    )


def environment_status() -> EnvironmentStatus:
    """Return a read-only runtime/host snapshot without probing the network."""
    return EnvironmentStatus(
        hostname=socket.gethostname(),
        platform=platform.system() or "unknown",
        platform_release=platform.release() or "unknown",
        architecture=platform.machine() or "unknown",
        python_version=platform.python_version() or sys.version.split()[0],
        cpu_count=os.cpu_count(),
    )


def file_freshness(path: str, max_age_seconds: float, *, now: datetime | None = None) -> FileFreshnessStatus:
    """Return a read-only freshness assessment for a regular file.

    This is useful for checking whether backups, exports, logs, or other expected
    artifacts are still being produced. Directories are rejected to keep the
    contract unambiguous. ``max_age_seconds`` must be finite and non-negative.
    """
    if not isinstance(max_age_seconds, (int, float)) or isinstance(max_age_seconds, bool):
        raise ValueError("max_age_seconds must be a finite non-negative number")
    if not (0 <= float(max_age_seconds) < float("inf")):
        raise ValueError("max_age_seconds must be a finite non-negative number")

    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    if not target.is_file():
        raise ValueError(f"Path is not a regular file: {target}")

    stat = target.stat()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    age_seconds = max(0.0, (current.astimezone(timezone.utc) - modified).total_seconds())
    threshold = float(max_age_seconds)
    return FileFreshnessStatus(
        path=str(target.resolve()),
        size_bytes=stat.st_size,
        modified_at=modified.isoformat().replace("+00:00", "Z"),
        age_seconds=round(age_seconds, 3),
        max_age_seconds=threshold,
        state="stale" if age_seconds > threshold else "ok",
    )
