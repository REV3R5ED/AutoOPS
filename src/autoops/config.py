"""Configuration loading for AutoOPS."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    """Small, explicit set of operator-controlled defaults."""

    json_output: bool = False
    disk_warning_percent: float = 90.0
    disk_min_free_gib: float | None = None

    @classmethod
    def from_mapping(cls, values: dict[str, Any]) -> "Config":
        allowed = {"json_output", "disk_warning_percent", "disk_min_free_gib"}
        unknown = sorted(set(values) - allowed)
        if unknown:
            raise ValueError(f"Unknown configuration key(s): {', '.join(unknown)}")

        json_output = values.get("json_output", False)
        if not isinstance(json_output, bool):
            raise ValueError("json_output must be a boolean")

        warning = values.get("disk_warning_percent", 90.0)
        if isinstance(warning, bool) or not isinstance(warning, (int, float)):
            raise ValueError("disk_warning_percent must be a number")
        warning = float(warning)
        if not 0 <= warning <= 100:
            raise ValueError("disk_warning_percent must be between 0 and 100")

        min_free = values.get("disk_min_free_gib")
        if min_free is not None:
            if isinstance(min_free, bool) or not isinstance(min_free, (int, float)):
                raise ValueError("disk_min_free_gib must be a number or null")
            min_free = float(min_free)
            if min_free < 0:
                raise ValueError("disk_min_free_gib must be greater than or equal to 0")

        return cls(
            json_output=json_output,
            disk_warning_percent=warning,
            disk_min_free_gib=min_free,
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
