"""Command-line interface for AutoOPS."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any

from autoops import __version__
from autoops.checks import (
    DiskStatus,
    disk_status,
    environment_status,
    file_freshness,
    log_growth_status,
    memory_status,
    systemd_service_status,
    tls_certificate_status,
)
from autoops.config import load_config
from autoops.operations import operation_from_check
from autoops.remote import (
    RemoteCheckError,
    parse_ssh_target,
    remote_disk_status,
    remote_environment_status,
    remote_memory_status,
)
from autoops.reporting import to_csv
from autoops.watch import SinkError, parse_sink, run_watch

PREFLIGHT_SCHEMA_VERSION = 4
REMOTE_PREFLIGHT_SCHEMA_VERSION = 5


def _output_group(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON")
    group.add_argument("--csv", action="store_true", dest="as_csv", help="Emit CSV")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autoops", description="Safe, observable automation utilities for IT operations."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="Path to an optional JSON configuration file")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include suppressed exception details in diagnostics (may expose sensitive runtime data)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    disk = subparsers.add_parser("disk", help="Inspect filesystem capacity (read-only)")
    disk.add_argument("path", nargs="?", default=".", help="Path to inspect")
    disk.add_argument(
        "--fail-on-warning", action="store_true", help="Return exit code 1 when a disk warning threshold is reached"
    )
    _output_group(disk)

    environment = subparsers.add_parser("environment", help="Inspect runtime and host environment (read-only)")
    _output_group(environment)

    freshness = subparsers.add_parser("freshness", help="Check whether a local file was updated recently (read-only)")
    freshness.add_argument("path", help="Regular file to inspect")
    freshness.add_argument(
        "--max-age-seconds", type=float, required=True, help="Maximum acceptable file age in seconds"
    )
    freshness.add_argument(
        "--fail-on-stale", action="store_true", help="Return exit code 1 when the file is stale or future-dated"
    )
    _output_group(freshness)

    preflight = subparsers.add_parser(
        "preflight", help="Run combined environment, disk, and memory health checks (read-only)"
    )
    preflight.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Local path whose filesystem capacity to inspect, or ssh://[user@]host[:port] for a remote preflight",
    )
    preflight.add_argument(
        "--fail-on-warning", action="store_true", help="Return exit code 1 when a disk warning threshold is reached"
    )
    preflight.add_argument(
        "--ssh-timeout",
        type=float,
        default=15.0,
        help="SSH connection timeout in seconds for remote preflight (default: 15)",
    )
    preflight.add_argument("--ssh-identity", help="SSH private key file for remote preflight (key-based auth only)")
    _output_group(preflight)

    memory = subparsers.add_parser("memory", help="Inspect host memory pressure (read-only)")
    memory.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return exit code 1 when memory pressure reaches the warning threshold",
    )
    _output_group(memory)

    systemd = subparsers.add_parser("systemd", help="Inspect one systemd unit's health (read-only, Linux)")
    systemd.add_argument("unit", help="Systemd unit name, e.g. ssh.service")
    systemd.add_argument(
        "--fail-on-warning", action="store_true", help="Return exit code 1 when the unit is not active"
    )
    _output_group(systemd)

    tls = subparsers.add_parser("tls", help="Check a remote TLS certificate's expiry (read-only handshake)")
    tls.add_argument("host", help="Hostname or IP address presenting the certificate")
    tls.add_argument("--port", type=int, default=443, help="TLS port (default: 443)")
    tls.add_argument("--warning-days", type=float, default=30.0, help="Warn when fewer days remain (default: 30)")
    tls.add_argument("--timeout", type=float, default=10.0, help="Connection timeout in seconds (default: 10)")
    tls.add_argument(
        "--fail-on-warning", action="store_true", help="Return exit code 1 when the certificate is expiring or expired"
    )
    _output_group(tls)

    loggrowth = subparsers.add_parser("loggrowth", help="Measure a log file's short-term growth rate (read-only)")
    loggrowth.add_argument("path", help="Regular log file to inspect")
    loggrowth.add_argument(
        "--interval-seconds", type=float, default=1.0, help="Seconds between size samples (default: 1.0)"
    )
    loggrowth.add_argument("--max-bytes-per-second", type=float, help="Warn when growth exceeds this rate")
    loggrowth.add_argument(
        "--fail-on-warning", action="store_true", help="Return exit code 1 when growth exceeds --max-bytes-per-second"
    )
    _output_group(loggrowth)

    watch = subparsers.add_parser(
        "watch", help="Periodically run checks and write redacted NDJSON audit events to a sink"
    )
    watch.add_argument(
        "--interval-seconds", type=float, default=300.0, help="Seconds between check runs (default: 300)"
    )
    watch.add_argument("--sink", required=True, help="Audit sink: file:<path>, syslog[:address], or http(s)://url")
    watch.add_argument(
        "--checks",
        default="disk,environment,memory",
        help="Comma-separated checks to run (default: disk,environment,memory)",
    )
    watch.add_argument("--path", default=".", help="Path for the disk check (default: .)")
    watch.add_argument(
        "--runs", type=int, default=0, help="Number of iterations; 0 runs until interrupted (default: 0)"
    )
    return parser


def _disk_state(status: DiskStatus, warning_percent: float, min_free_gib: float | None) -> tuple[str, str]:
    reasons: list[str] = []
    if status.used_percent >= warning_percent:
        reasons.append("used_percent")
    if min_free_gib is not None and status.free_bytes < min_free_gib * (1024**3):
        reasons.append("min_free_gib")
    return ("warning", ",".join(reasons)) if reasons else ("ok", "")


def _preflight_payload(path: str, warning_percent: float, min_free_gib: float | None) -> dict[str, object]:
    environment = environment_status()
    disk = disk_status(path)
    state, reason = _disk_state(disk, warning_percent, min_free_gib)
    return {
        "schema_version": PREFLIGHT_SCHEMA_VERSION,
        "autoops_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall_state": state,
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
        "disk_warning_reason": reason,
        "disk_warning_percent": warning_percent,
        "disk_min_free_gib": min_free_gib,
    }


def _remote_preflight_payload(
    spec: str,
    warning_percent: float,
    min_free_gib: float | None,
    memory_warning_percent: float,
    ssh_timeout: float,
    ssh_identity: str | None,
) -> dict[str, object]:
    """Build a preflight report for a remote host reached over SSH.

    Uses schema version 5: the local preflight fields plus ``remote_host``
    and remote memory fields. Fields that cannot be collected through the
    read-only remote probes (remote Python version) are null.
    """
    target = parse_ssh_target(spec)
    environment = remote_environment_status(target, timeout=ssh_timeout, identity_file=ssh_identity)
    disk = remote_disk_status(target, "/", timeout=ssh_timeout, identity_file=ssh_identity)
    memory = remote_memory_status(target, timeout=ssh_timeout, identity_file=ssh_identity)

    disk_used_percent = float(disk["used_percent"])
    disk_free_bytes = int(disk["free_bytes"])
    reasons: list[str] = []
    if disk_used_percent >= warning_percent:
        reasons.append("used_percent")
    if min_free_gib is not None and disk_free_bytes < min_free_gib * (1024**3):
        reasons.append("min_free_gib")
    disk_state = "warning" if reasons else "ok"
    memory_state = "warning" if float(memory["used_percent"]) >= memory_warning_percent else "ok"
    overall_state = "warning" if disk_state == "warning" or memory_state == "warning" else "ok"

    return {
        "schema_version": REMOTE_PREFLIGHT_SCHEMA_VERSION,
        "autoops_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "overall_state": overall_state,
        "remote_host": target.label(),
        "hostname": environment["hostname"],
        "platform": environment["platform"],
        "platform_release": environment["platform_release"],
        "architecture": environment["architecture"],
        "python_version": None,
        "cpu_count": environment["cpu_count"],
        "disk_path": disk["path"],
        "disk_total_bytes": disk["total_bytes"],
        "disk_used_bytes": disk["used_bytes"],
        "disk_free_bytes": disk["free_bytes"],
        "disk_used_percent": disk_used_percent,
        "disk_state": disk_state,
        "disk_warning_reason": ",".join(reasons),
        "disk_warning_percent": warning_percent,
        "disk_min_free_gib": min_free_gib,
        "memory_total_bytes": memory["total_bytes"],
        "memory_used_bytes": memory["used_bytes"],
        "memory_used_percent": memory["used_percent"],
        "memory_state": memory_state,
        "memory_warning_percent": memory_warning_percent,
    }


def _watch_operations(checks: str, path: str, memory_warning_percent: float) -> list:
    """Build the read-only check operations for one watch iteration."""
    builders = {
        "disk": lambda: operation_from_check("watch-disk", disk_status, path),
        "environment": lambda: operation_from_check("watch-environment", environment_status),
        "memory": lambda: operation_from_check("watch-memory", memory_status, memory_warning_percent),
    }
    names = [name.strip() for name in checks.split(",")]
    if not names or any(not name for name in names):
        raise ValueError("--checks must be a non-empty comma-separated list")
    unknown = [name for name in names if name not in builders]
    if unknown:
        raise ValueError(f"unknown watch check(s): {', '.join(unknown)}; allowed: {', '.join(sorted(builders))}")
    return [builders[name]() for name in names]


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.command == "disk":
        try:
            disk_info = disk_status(args.path)
        except (FileNotFoundError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        state, reason = _disk_state(disk_info, config.disk_warning_percent, config.disk_min_free_gib)
        disk_payload: dict[str, Any] = disk_info.to_dict()
        disk_payload.update(
            {
                "state": state,
                "warning_reason": reason,
                "warning_percent": config.disk_warning_percent,
                "min_free_gib": config.disk_min_free_gib,
            }
        )
        if args.as_csv:
            print(
                to_csv(
                    disk_payload,
                    fields=(
                        "path",
                        "total_bytes",
                        "used_bytes",
                        "free_bytes",
                        "used_percent",
                        "state",
                        "warning_reason",
                        "warning_percent",
                        "min_free_gib",
                    ),
                ),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(disk_payload, sort_keys=True))
        else:
            gib = 1024**3
            print(f"Path: {disk_info.path}")
            print(
                f"Used: {disk_info.used_bytes / gib:.2f} GiB / {disk_info.total_bytes / gib:.2f} GiB ({disk_info.used_percent:.2f}%)"
            )
            print(f"Free: {disk_info.free_bytes / gib:.2f} GiB")
            threshold = f"warning at {config.disk_warning_percent:.1f}%"
            if config.disk_min_free_gib is not None:
                threshold += f", minimum free {config.disk_min_free_gib:.2f} GiB"
            print(f"State: {state} ({threshold})")
            if reason:
                print(f"Warning reason: {reason}")
        return 1 if args.fail_on_warning and state == "warning" else 0

    if args.command == "environment":
        env_info = environment_status()
        env_payload: dict[str, Any] = env_info.to_dict()
        if args.as_csv:
            print(
                to_csv(
                    env_payload,
                    fields=("hostname", "platform", "platform_release", "architecture", "python_version", "cpu_count"),
                ),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(env_payload, sort_keys=True))
        else:
            print(f"Hostname: {env_info.hostname}")
            print(f"Platform: {env_info.platform} {env_info.platform_release} ({env_info.architecture})")
            print(f"Python: {env_info.python_version}")
            print(f"CPU count: {env_info.cpu_count if env_info.cpu_count is not None else 'unknown'}")
        return 0

    if args.command == "freshness":
        try:
            fresh_info = file_freshness(args.path, args.max_age_seconds)
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        fresh_payload: dict[str, Any] = fresh_info.to_dict()
        if args.as_csv:
            print(
                to_csv(
                    fresh_payload,
                    fields=("path", "size_bytes", "modified_at", "age_seconds", "max_age_seconds", "state"),
                ),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(fresh_payload, sort_keys=True))
        else:
            print(f"Path: {fresh_info.path}")
            print(f"Modified: {fresh_info.modified_at}")
            print(f"Age: {fresh_info.age_seconds:.3f}s (maximum {fresh_info.max_age_seconds:.3f}s)")
            print(f"State: {fresh_info.state}")
        return 1 if args.fail_on_stale and fresh_info.state in {"stale", "future"} else 0

    if args.command == "preflight":
        if args.path.startswith("ssh://"):
            try:
                remote_payload: dict[str, Any] = _remote_preflight_payload(
                    args.path,
                    config.disk_warning_percent,
                    config.disk_min_free_gib,
                    config.memory_warning_percent,
                    args.ssh_timeout,
                    args.ssh_identity,
                )
            except (ValueError, RemoteCheckError) as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            remote_fields: tuple[str, ...] = (
                "schema_version",
                "autoops_version",
                "generated_at",
                "overall_state",
                "remote_host",
                "hostname",
                "platform",
                "platform_release",
                "architecture",
                "python_version",
                "cpu_count",
                "disk_path",
                "disk_total_bytes",
                "disk_used_bytes",
                "disk_free_bytes",
                "disk_used_percent",
                "disk_state",
                "disk_warning_reason",
                "disk_warning_percent",
                "disk_min_free_gib",
                "memory_total_bytes",
                "memory_used_bytes",
                "memory_used_percent",
                "memory_state",
                "memory_warning_percent",
            )
            if args.as_csv:
                print(to_csv(remote_payload, fields=remote_fields), end="")
            elif args.as_json or config.json_output:
                print(json.dumps(remote_payload, sort_keys=True))
            else:
                print(
                    f"Report schema: v{remote_payload['schema_version']} | AutoOPS: {remote_payload['autoops_version']}"
                )
                print(f"Generated: {remote_payload['generated_at']}")
                print(f"Remote host: {remote_payload['remote_host']} (via SSH)")
                print(f"Overall state: {remote_payload['overall_state']}")
                print(
                    f"Host: {remote_payload['hostname']} — {remote_payload['platform']} {remote_payload['platform_release']} ({remote_payload['architecture']})"
                )
                print(
                    f"Disk: {remote_payload['disk_path']} — {remote_payload['disk_used_percent']:.2f}% used ({remote_payload['disk_state']})"
                )
                print(f"Memory: {remote_payload['memory_used_percent']:.2f}% used ({remote_payload['memory_state']})")
            return 1 if args.fail_on_warning and remote_payload["overall_state"] == "warning" else 0

        try:
            preflight_payload: dict[str, Any] = _preflight_payload(
                args.path, config.disk_warning_percent, config.disk_min_free_gib
            )
        except (FileNotFoundError, OSError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        preflight_fields: tuple[str, ...] = (
            "schema_version",
            "autoops_version",
            "generated_at",
            "overall_state",
            "hostname",
            "platform",
            "platform_release",
            "architecture",
            "python_version",
            "cpu_count",
            "disk_path",
            "disk_total_bytes",
            "disk_used_bytes",
            "disk_free_bytes",
            "disk_used_percent",
            "disk_state",
            "disk_warning_reason",
            "disk_warning_percent",
            "disk_min_free_gib",
        )
        if args.as_csv:
            print(to_csv(preflight_payload, fields=preflight_fields), end="")
        elif args.as_json or config.json_output:
            print(json.dumps(preflight_payload, sort_keys=True))
        else:
            print(
                f"Report schema: v{preflight_payload['schema_version']} | AutoOPS: {preflight_payload['autoops_version']}"
            )
            print(f"Generated: {preflight_payload['generated_at']}")
            print(f"Overall state: {preflight_payload['overall_state']}")
            print(
                f"Host: {preflight_payload['hostname']} — {preflight_payload['platform']} {preflight_payload['platform_release']} ({preflight_payload['architecture']})"
            )
            print(
                f"Python: {preflight_payload['python_version']} | CPU count: {preflight_payload['cpu_count'] if preflight_payload['cpu_count'] is not None else 'unknown'}"
            )
            print(f"Disk: {preflight_payload['disk_path']} — {preflight_payload['disk_used_percent']:.2f}% used")
            threshold = f"warning at {preflight_payload['disk_warning_percent']:.1f}%"
            if preflight_payload["disk_min_free_gib"] is not None:
                threshold += f", minimum free {preflight_payload['disk_min_free_gib']:.2f} GiB"
            print(f"State: {preflight_payload['disk_state']} ({threshold})")
            if preflight_payload["disk_warning_reason"]:
                print(f"Warning reason: {preflight_payload['disk_warning_reason']}")
        return 1 if args.fail_on_warning and preflight_payload["overall_state"] == "warning" else 0

    if args.command == "memory":
        try:
            mem_info = memory_status(config.memory_warning_percent)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        mem_payload: dict[str, Any] = mem_info.to_dict()
        if args.as_csv:
            print(
                to_csv(
                    mem_payload,
                    fields=("total_bytes", "available_bytes", "used_bytes", "used_percent", "warning_percent", "state"),
                ),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(mem_payload, sort_keys=True))
        else:
            gib = 1024**3
            print(
                f"Memory: {mem_info.used_bytes / gib:.2f} GiB / {mem_info.total_bytes / gib:.2f} GiB used ({mem_info.used_percent:.2f}%)"
            )
            print(f"Available: {mem_info.available_bytes / gib:.2f} GiB")
            print(f"State: {mem_info.state} (warning at {mem_info.warning_percent:.1f}%)")
        return 1 if args.fail_on_warning and mem_info.state == "warning" else 0

    if args.command == "systemd":
        try:
            unit_info = systemd_service_status(args.unit)
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        unit_payload: dict[str, Any] = unit_info.to_dict()
        if args.as_csv:
            print(to_csv(unit_payload, fields=("unit", "active_state", "sub_state", "load_state", "state")), end="")
        elif args.as_json or config.json_output:
            print(json.dumps(unit_payload, sort_keys=True))
        else:
            print(f"Unit: {unit_info.unit}")
            print(f"Active: {unit_info.active_state} ({unit_info.sub_state})")
            print(f"Load: {unit_info.load_state}")
            print(f"State: {unit_info.state}")
        return 1 if args.fail_on_warning and unit_info.state != "active" else 0

    if args.command == "tls":
        try:
            cert_info = tls_certificate_status(
                args.host, args.port, warning_days=args.warning_days, timeout=args.timeout
            )
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        cert_payload: dict[str, Any] = cert_info.to_dict()
        if args.as_csv:
            print(
                to_csv(cert_payload, fields=("host", "port", "not_after", "days_remaining", "warning_days", "state")),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(cert_payload, sort_keys=True))
        else:
            print(f"Host: {cert_info.host}:{cert_info.port}")
            print(f"Expires: {cert_info.not_after} ({cert_info.days_remaining:.1f} days remaining)")
            print(f"State: {cert_info.state} (warning within {cert_info.warning_days:.0f} days)")
        return 1 if args.fail_on_warning and cert_info.state in {"warning", "expired"} else 0

    if args.command == "loggrowth":
        try:
            growth_info = log_growth_status(
                args.path,
                interval_seconds=args.interval_seconds,
                max_bytes_per_second=args.max_bytes_per_second,
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        growth_payload: dict[str, Any] = growth_info.to_dict()
        if args.as_csv:
            print(
                to_csv(
                    growth_payload,
                    fields=(
                        "path",
                        "size_bytes",
                        "previous_size_bytes",
                        "interval_seconds",
                        "growth_bytes",
                        "growth_bytes_per_second",
                        "max_bytes_per_second",
                        "state",
                    ),
                ),
                end="",
            )
        elif args.as_json or config.json_output:
            print(json.dumps(growth_payload, sort_keys=True))
        else:
            print(f"Path: {growth_info.path}")
            print(
                f"Growth: {growth_info.growth_bytes} bytes over {growth_info.interval_seconds:.2f}s ({growth_info.growth_bytes_per_second:.2f} B/s)"
            )
            if growth_info.max_bytes_per_second is not None:
                print(f"Maximum: {growth_info.max_bytes_per_second:.2f} B/s")
            print(f"State: {growth_info.state}")
        return 1 if args.fail_on_warning and growth_info.state == "warning" else 0

    if args.command == "watch":
        try:
            operations = _watch_operations(args.checks, args.path, config.memory_warning_percent)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        try:
            sink = parse_sink(args.sink)
        except SinkError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return run_watch(
            operations,
            sink,
            interval_seconds=args.interval_seconds,
            runs=args.runs,
            verbose=args.verbose,
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
