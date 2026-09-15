"""Read-only system health checks used by AutoOPS."""

from __future__ import annotations

from dataclasses import asdict, dataclass
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
