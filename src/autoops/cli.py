"""Command-line interface for AutoOPS."""

from __future__ import annotations

import argparse
import json

from autoops import __version__
from autoops.checks import disk_status


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoops",
        description="Safe, observable automation utilities for IT operations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    disk = subparsers.add_parser("disk", help="Inspect filesystem capacity (read-only)")
    disk.add_argument("path", nargs="?", default=".", help="Path to inspect")
    disk.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "disk":
        try:
            status = disk_status(args.path)
        except (FileNotFoundError, OSError) as exc:
            print(f"error: {exc}")
            return 2

        if args.as_json:
            print(json.dumps(status.to_dict(), sort_keys=True))
        else:
            gib = 1024 ** 3
            print(f"Path: {status.path}")
            print(f"Used: {status.used_bytes / gib:.2f} GiB / {status.total_bytes / gib:.2f} GiB ({status.used_percent:.2f}%)")
            print(f"Free: {status.free_bytes / gib:.2f} GiB")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
