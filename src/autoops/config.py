"""Configuration loading for AutoOPS."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Default percentage of used filesystem capacity that triggers a disk warning.
DEFAULT_DISK_WARNING_PERCENT = 90.0
#: Default percentage of used memory that triggers a memory warning.
DEFAULT_MEMORY_WARNING_PERCENT = 90.0


@dataclass(frozen=True)
class Config:
    """Small, explicit set of operator-controlled defaults."""

    json_output: bool = False
    disk_warning_percent: float = DEFAULT_DISK_WARNING_PERCENT
    disk_min_free_gib: float | None = None
    memory_warning_percent: float = DEFAULT_MEMORY_WARNING_PERCENT

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> Config:
        allowed = {"json_output", "disk_warning_percent", "disk_min_free_gib", "memory_warning_percent"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration key(s): {', '.join(unknown)}")

        json_output = values.get("json_output", False)
        if not isinstance(json_output, bool):
            raise ValueError("json_output must be a boolean")

        warning = values.get("disk_warning_percent", DEFAULT_DISK_WARNING_PERCENT)
        if isinstance(warning, bool) or not isinstance(warning, (int, float)):
            raise ValueError("disk_warning_percent must be a number")
        warning = float(warning)
        if not math.isfinite(warning):
            raise ValueError("disk_warning_percent must be finite")
        if not 0 <= warning <= 100:
            raise ValueError("disk_warning_percent must be between 0 and 100")

        min_free = values.get("disk_min_free_gib")
        if min_free is not None:
            if isinstance(min_free, bool) or not isinstance(min_free, (int, float)):
                raise ValueError("disk_min_free_gib must be a number or null")
            min_free = float(min_free)
            if not math.isfinite(min_free):
                raise ValueError("disk_min_free_gib must be finite")
            if min_free < 0:
                raise ValueError("disk_min_free_gib must be greater than or equal to 0")

        memory_warning = values.get("memory_warning_percent", DEFAULT_MEMORY_WARNING_PERCENT)
        if isinstance(memory_warning, bool) or not isinstance(memory_warning, (int, float)):
            raise ValueError("memory_warning_percent must be a number")
        memory_warning = float(memory_warning)
        if not math.isfinite(memory_warning):
            raise ValueError("memory_warning_percent must be finite")
        if not 0 <= memory_warning <= 100:
            raise ValueError("memory_warning_percent must be between 0 and 100")

        return cls(
            json_output=json_output,
            disk_warning_percent=warning,
            disk_min_free_gib=min_free,
            memory_warning_percent=memory_warning,
        )


def load_config(path: str | Path | None) -> Config:
    """Load a JSON config file, or return safe defaults when none is supplied."""

    if path is None:
        return Config()

    config_path = Path(path).expanduser()
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Configuration file does not exist: {config_path}") from exc
    except OSError as exc:
        raise ValueError(f"Could not read configuration file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON configuration: {exc.msg}") from exc

    if not isinstance(raw, dict):
        raise ValueError("Configuration root must be a JSON object")
    return Config.from_mapping(raw)
