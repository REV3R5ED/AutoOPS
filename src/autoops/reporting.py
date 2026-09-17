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
    diagnostic text. Some spreadsheet applications ignore leading whitespace
    before deciding whether a cell is a formula, so detection skips all Unicode
    whitespace while preserving the original value. Prefixing formula-like
    strings with an apostrophe keeps them literal while leaving numeric values
    and ordinary strings unchanged.
    """
    if isinstance(value, str):
        candidate = value.lstrip()
        if candidate.startswith(_FORMULA_PREFIXES):
            return "'" + value
    return value


def to_csv(payload: Mapping[str, Any], *, fields: tuple[str, ...]) -> str:
    """Serialize one flat result as a deterministic, spreadsheet-safe CSV report.

    Callers provide the schema explicitly so report columns remain stable across
    Python versions and implementation details. Nested values are intentionally
    rejected: command reports should expose a simple, spreadsheet-friendly row.
    Formula-like strings are neutralized even when preceded by Unicode whitespace
    that spreadsheet applications may ignore before formula interpretation.
    """
    unknown = set(payload) - set(fields)
    if unknown:
        raise ValueError(f"CSV schema does not include fields: {', '.join(sorted(unknown))}")

    for key, value in payload.items():
        if isinstance(value, (dict, list, tuple, set)):
            raise ValueError(f"CSV field {key!r} must contain a scalar value")

    stream = io.StringIO(newline="")
    # CRLF is the CSV convention and, importantly, makes the csv module quote
    # fields containing either CR or LF consistently across supported Python
    # versions. A lone LF terminator can leave embedded CR unquoted on 3.10.
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    writer.writerow({field: _spreadsheet_safe(payload.get(field, "")) for field in fields})
    return stream.getvalue()
