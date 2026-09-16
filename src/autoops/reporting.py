"""Deterministic report serialization for AutoOPS command results."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any


_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _spreadsheet_safe(value: Any) -> Any:
    """Neutralize string values that spreadsheet apps may treat as formulas.

    CSV reports can contain operator-controlled paths, hostnames, or future
    diagnostic text. Prefixing formula-like strings with an apostrophe keeps
    them literal when a report is opened interactively in common spreadsheet
    applications while leaving numeric values and ordinary strings unchanged.
    """
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def to_csv(payload: Mapping[str, Any], *, fields: tuple[str, ...]) -> str:
    """Serialize one flat result as a deterministic, spreadsheet-safe CSV report.

    Callers provide the schema explicitly so report columns remain stable across
    Python versions and implementation details. Nested values are intentionally
    rejected: command reports should expose a simple, spreadsheet-friendly row.
    String values beginning with common spreadsheet formula prefixes are
    neutralized to prevent formula execution when exported reports are opened.
    """
    unknown = set(payload) - set(fields)
    if unknown:
        raise ValueError(f"CSV schema does not include fields: {', '.join(sorted(unknown))}")

    for key, value in payload.items():
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(f"CSV field {key!r} must contain a scalar value")

    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerow({field: _spreadsheet_safe(payload.get(field, "")) for field in fields})
    return stream.getvalue()
