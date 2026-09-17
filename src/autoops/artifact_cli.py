"""Command-line interface for read-only artifact health checks."""

from __future__ import annotations

import argparse
import json

from autoops.artifacts import artifact_health
from autoops.reporting import to_csv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoops-artifact",
        description="Assess local artifact freshness and minimum size (read-only).",
    )
    parser.add_argument("path", help="Regular file to inspect")
    parser.add_argument(
        "--max-age-seconds",
        type=float,
        required=True,
        help="Maximum acceptable file age in seconds",
    )
    parser.add_argument(
        "--min-size-bytes",
        type=int,
        default=0,
        help="Minimum acceptable file size in bytes (default: 0)",
    )
    parser.add_argument(
        "--fail-on-unhealthy",
        action="store_true",
        help="Return exit code 1 for stale, future-dated, or undersized artifacts",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    output.add_argument("--csv", action="store_true", dest="as_csv", help="Emit CSV")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        status = artifact_health(
            args.path,
            args.max_age_seconds,
            min_size_bytes=args.min_size_bytes,
        )
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2

    payload = status.to_dict()
    fields = (
        "path",
        "size_bytes",
        "modified_at",
        "age_seconds",
        "max_age_seconds",
        "min_size_bytes",
        "state",
    )
    if args.as_csv:
        print(to_csv(payload, fields=fields), end="")
    elif args.as_json:
        print(json.dumps(payload, sort_keys=True))
    else:
        print(f"Path: {status.path}")
        print(f"Modified: {status.modified_at}")
        print(f"Size: {status.size_bytes} bytes (minimum {status.min_size_bytes})")
        print(f"Age: {status.age_seconds:.3f}s (maximum {status.max_age_seconds:.3f}s)")
        print(f"State: {status.state}")

    return 1 if args.fail_on_unhealthy and status.state != "ok" else 0


if __name__ == "__main__":
    raise SystemExit(main())
