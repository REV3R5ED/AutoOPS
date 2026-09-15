"""Command-line interface for AutoOPS."""

from __future__ import annotations

import argparse
import json

from autoops import __version__
from autoops.checks import disk_status, environment_status
from autoops.config import load_config


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoops",
        description="Safe, observable automation utilities for IT operations.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Path to an optional JSON configuration file")
    subparsers = parser.add_subparsers(dest="command", required=True)

    disk = subparsers.add_parser("disk", help="Inspect filesystem capacity (read-only)")
    disk.add_argument("path", nargs="?", default=".", help="Path to inspect")
    disk.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")

    environment = subparsers.add_parser(
        "environment", help="Inspect runtime and host environment (read-only)"
    )
    environment.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"error: {exc}")
        return 2

    if args.command == "disk":
        try:
            status = disk_status(args.path)
        except (FileNotFoundError, OSError) as exc:
            print(f"error: {exc}")
            return 2

        as_json = args.as_json or config.json_output
        state = "warning" if status.used_percent >= config.disk_warning_percent else "ok"
        if as_json:
            payload = status.to_dict()
            payload.update({"state": state, "warning_percent": config.disk_warning_percent})
            print(json.dumps(payload, sort_keys=True))
        else:
            gib = 1024 ** 3
            print(f"Path: {status.path}")
            print(f"Used: {status.used_bytes / gib:.2f} GiB / {status.total_bytes / gib:.2f} GiB ({status.used_percent:.2f}%)")
            print(f"Free: {status.free_bytes / gib:.2f} GiB")
            print(f"State: {state} (warning at {config.disk_warning_percent:.1f}%)")
        return 0

    if args.command == "environment":
        status = environment_status()
        as_json = args.as_json or config.json_output
        if as_json:
            print(json.dumps(status.to_dict(), sort_keys=True))
        else:
            print(f"Hostname: {status.hostname}")
            print(f"Platform: {status.platform} {status.platform_release} ({status.architecture})")
            print(f"Python: {status.python_version}")
            print(f"CPU count: {status.cpu_count if status.cpu_count is not None else 'unknown'}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
