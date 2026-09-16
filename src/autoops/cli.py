"""Command-line interface for AutoOPS."""

from __future__ import annotations

import argparse
import json

from autoops import __version__
from autoops.checks import disk_status, environment_status
from autoops.config import load_config
from autoops.reporting import to_csv


def _output_group(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    group.add_argument("--csv", action="store_true", dest="as_csv", help="Emit CSV")


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
    disk.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 1 when disk usage meets the warning threshold",
    )
    _output_group(disk)

    environment = subparsers.add_parser(
        "environment", help="Inspect runtime and host environment (read-only)"
    )
    _output_group(environment)

    preflight = subparsers.add_parser(
        "preflight", help="Run combined local environment and disk health checks (read-only)"
    )
    preflight.add_argument("path", nargs="?", default=".", help="Path whose filesystem capacity to inspect")
    preflight.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 1 when disk usage meets the warning threshold",
    )
    _output_group(preflight)
    return parser


def _preflight_payload(path: str, warning_percent: float) -> dict[str, object]:
    environment = environment_status()
    disk = disk_status(path)
    state = "warning" if disk.used_percent >= warning_percent else "ok"
    return {
        "hostname": environment.hostname,
        "platform": environment.platform,
        "platform_release": environment.platform_release,
        "architecture": environment.architecture,
        "python_version": environment.python_version,
        "cpu_count": environment.cpu_count,
        "disk_path": disk.path,
        "disk_total_bytes": disk.total_bytes,
        "disk_used_bytes": disk.used_bytes,
        "disk_free_bytes": disk.free_bytes,
        "disk_used_percent": disk.used_percent,
        "disk_state": state,
        "disk_warning_percent": warning_percent,
    }


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

        state = "warning" if status.used_percent >= config.disk_warning_percent else "ok"
        payload = status.to_dict()
        payload.update({"state": state, "warning_percent": config.disk_warning_percent})
        if args.as_csv:
            print(to_csv(payload, fields=("path", "total_bytes", "used_bytes", "free_bytes", "used_percent", "state", "warning_percent")), end="")
        elif args.as_json or config.json_output:
            print(json.dumps(payload, sort_keys=True))
        else:
            gib = 1024 ** 3
            print(f"Path: {status.path}")
            print(f"Used: {status.used_bytes / gib:.2f} GiB / {status.total_bytes / gib:.2f} GiB ({status.used_percent:.2f}%)")
            print(f"Free: {status.free_bytes / gib:.2f} GiB")
            print(f"State: {state} (warning at {config.disk_warning_percent:.1f}%)")
        return 1 if args.fail_on_warning and state == "warning" else 0

    if args.command == "environment":
        status = environment_status()
        payload = status.to_dict()
        if args.as_csv:
            print(to_csv(payload, fields=("hostname", "platform", "platform_release", "architecture", "python_version", "cpu_count")), end="")
        elif args.as_json or config.json_output:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"Hostname: {status.hostname}")
            print(f"Platform: {status.platform} {status.platform_release} ({status.architecture})")
            print(f"Python: {status.python_version}")
            print(f"CPU count: {status.cpu_count if status.cpu_count is not None else 'unknown'}")
        return 0

    if args.command == "preflight":
        try:
            payload = _preflight_payload(args.path, config.disk_warning_percent)
        except (FileNotFoundError, OSError) as exc:
            print(f"error: {exc}")
            return 2

        fields = (
            "hostname", "platform", "platform_release", "architecture", "python_version", "cpu_count",
            "disk_path", "disk_total_bytes", "disk_used_bytes", "disk_free_bytes", "disk_used_percent",
            "disk_state", "disk_warning_percent",
        )
        if args.as_csv:
            print(to_csv(payload, fields=fields), end="")
        elif args.as_json or config.json_output:
            print(json.dumps(payload, sort_keys=True))
        else:
            print(f"Host: {payload['hostname']} — {payload['platform']} {payload['platform_release']} ({payload['architecture']})")
            print(f"Python: {payload['python_version']} | CPU count: {payload['cpu_count'] if payload['cpu_count'] is not None else 'unknown'}")
            print(f"Disk: {payload['disk_path']} — {payload['disk_used_percent']:.2f}% used")
            print(f"State: {payload['disk_state']} (warning at {payload['disk_warning_percent']:.1f}%)")
        return 1 if args.fail_on_warning and payload["disk_state"] == "warning" else 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
