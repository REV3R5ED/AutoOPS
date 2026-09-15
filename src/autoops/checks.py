"""Read-only system health checks used by AutoOPS."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import shutil
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
