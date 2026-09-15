"""Deterministic report serialization for AutoOPS command results."""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping
from typing import Any


def to_csv(payload: Mapping[str, Any], *, fields: tuple[str, ...]) -> str:
    """Serialize one flat result as a deterministic CSV report.

    Callers provide the schema explicitly so report columns remain stable across
    Python versions and implementation details. Nested values are intentionally
    rejected: command reports should expose a simple, spreadsheet-friendly row.
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
    writer.writerow({field: payload.get(field, "") for field in fields})
    return stream.getvalue()
