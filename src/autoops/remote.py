"""Read-only remote health checks over SSH for AutoOPS fleet workflows.

Remote checks reuse the local check semantics (disk, environment, memory) but
collect the data on another host through the operator's ``ssh`` client. The
module is deliberately narrow:

- Host-key policy is strict: unknown host keys are never auto-accepted. The
  target host's key must already be present in the operator's known_hosts
  file (populated out of band, e.g. with a first manual ``ssh`` connection).
- Only an explicit allowlist of read-only commands may run remotely. Command
  arguments are validated and passed as ``ssh`` argv elements; no remote
  command text is ever assembled from untrusted input without quoting.
- Authentication is key-based only (``BatchMode=yes``): no password prompts,
  no credential handling.
- Remote checks are read-only and integrate with the existing
  :class:`~autoops.operations.Operation` contract, so fleet workflows keep the
  dry-run-first safety semantics.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autoops.operations import Operation

_SSH_TIMEOUT_SECONDS = 15
_HOST_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
_IPV6_PATTERN = re.compile(r"^\[[0-9a-fA-F:.]+\]$")
_USER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_PATH_FORBIDDEN = re.compile(r"[\x00-\x1f\x7f]")


class RemoteCheckError(OSError):
    """Raised when a remote check cannot be performed safely or fails."""


@dataclass(frozen=True)
class SshTarget:
    """A validated SSH connection target parsed from an ``ssh://`` spec."""

    user: str | None
    host: str
    port: int | None

    def destination(self) -> str:
        """Return the ``[user@]host`` destination argument for ``ssh``."""
        return f"{self.user}@{self.host}" if self.user else self.host

    def label(self) -> str:
        """Return a stable, human-friendly label for reports and audit events."""
        label = self.destination()
        return f"{label}:{self.port}" if self.port else label


def parse_ssh_target(spec: str) -> SshTarget:
    """Parse and strictly validate an ``ssh://[user@]host[:port]`` spec.

    Anything that is not exactly this shape — paths, query strings, ssh
    option flags, whitespace, or control characters — is rejected so a
    crafted target cannot smuggle extra arguments to the ``ssh`` command.
    """
    if not isinstance(spec, str):
        raise ValueError("ssh target must be a string")
    if not spec.startswith("ssh://"):
        raise ValueError("ssh target must start with 'ssh://'")
    remainder = spec[len("ssh://") :]
    if not remainder or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in remainder):
        raise ValueError("ssh target must not be empty or contain whitespace/control characters")
    if "/" in remainder or "?" in remainder or "#" in remainder:
        raise ValueError("ssh target must be 'ssh://[user@]host[:port]' without paths or query strings")

    user: str | None = None
    if "@" in remainder:
        user, _, remainder = remainder.partition("@")
        if not _USER_PATTERN.match(user or ""):
            raise ValueError(f"invalid ssh user in target: {spec!r}")

    host = remainder
    port: int | None = None
    if host.startswith("["):
        # Bracketed IPv6 literal, optionally with :port.
        match = re.fullmatch(r"(\[[0-9a-fA-F:.]+\])(?::(\d+))?", host)
        if not match:
            raise ValueError(f"invalid ssh target: {spec!r}")
        host, port_text = match.group(1), match.group(2)
    elif host.count(":") > 1:
        raise ValueError(f"invalid ssh target: {spec!r}; IPv6 literals must be bracketed")
    elif ":" in host:
        host, _, port_text = host.partition(":")
    else:
        port_text = None

    if not _HOST_PATTERN.match(host) and not _IPV6_PATTERN.match(host):
        raise ValueError(f"invalid ssh host in target: {spec!r}")
    if host.startswith("-"):
        raise ValueError(f"invalid ssh host in target: {spec!r}")
    if port_text is not None:
        if not port_text.isdigit():
            raise ValueError(f"invalid ssh port in target: {spec!r}")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise ValueError(f"ssh port out of range in target: {spec!r}")

    return SshTarget(user=user, host=host, port=port)


def _validate_remote_path(path: str) -> str:
    if not isinstance(path, str) or not path:
        raise ValueError("remote path must be a non-empty string")
    if _PATH_FORBIDDEN.search(path):
        raise ValueError("remote path must not contain control characters")
    if not path.startswith("/"):
        raise ValueError("remote path must be absolute")
    return path


def _disk_command(path: str) -> str:
    # POSIX df (-P) output is machine-parseable: the 5th field is "Capacity"
    # like "42%". The path is shell-quoted; never interpolated raw.
    return f"df -kP -- {shlex.quote(_validate_remote_path(path))}"


def _environment_command() -> str:
    # One compound read-only probe; output lines are parsed positionally.
    return (
        "hostname; uname -s; uname -r; uname -m; (nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo unknown)"
    )


def _memory_command() -> str:
    return "grep -E '^(MemTotal|MemAvailable):' /proc/meminfo"


# Allowlist of remote checks: name -> command builder. Only these commands may
# ever be executed on a remote host through this module.
REMOTE_CHECK_COMMANDS: dict[str, Callable[..., str]] = {
    "disk": _disk_command,
    "environment": _environment_command,
    "memory": _memory_command,
}


def _ssh_argv(
    target: SshTarget,
    remote_command: str,
    *,
    timeout: float,
    identity_file: str | None,
) -> list[str]:
    if shutil.which("ssh") is None:
        raise RemoteCheckError("the 'ssh' executable was not found on this host")
    argv = [
        "ssh",
        "-n",  # never read stdin; prevents hanging on prompts
        "-o",
        "BatchMode=yes",  # key-based auth only; no password prompts
        "-o",
        "StrictHostKeyChecking=yes",  # never auto-accept unknown host keys
        "-o",
        f"ConnectTimeout={int(timeout)}",
    ]
    if identity_file is not None:
        argv.extend(["-i", identity_file])
    if target.port is not None:
        argv.extend(["-p", str(target.port)])
    argv.extend(["--", target.destination(), remote_command])
    return argv


def _validate_ssh_options(timeout: float, identity_file: str | None) -> tuple[float, str | None]:
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("ssh timeout must be a number")
    timeout = float(timeout)
    if not (1 <= timeout <= 300):
        raise ValueError("ssh timeout must be between 1 and 300 seconds")
    identity: str | None = None
    if identity_file is not None:
        if not isinstance(identity_file, str) or not identity_file:
            raise ValueError("ssh identity file must be a non-empty string")
        candidate = Path(identity_file).expanduser()
        if not candidate.is_file():
            raise ValueError(f"ssh identity file does not exist: {candidate}")
        identity = str(candidate)
    return timeout, identity


def run_remote_check(
    target: SshTarget,
    check: str,
    *args: str,
    timeout: float = _SSH_TIMEOUT_SECONDS,
    identity_file: str | None = None,
) -> str:
    """Execute one allowlisted remote check and return its raw stdout.

    ``check`` must be a key of :data:`REMOTE_CHECK_COMMANDS`; anything else
    is rejected. Raises :class:`RemoteCheckError` when ssh is unavailable,
    the host key is unknown, authentication fails, or the remote command
    exits non-zero.
    """
    if check not in REMOTE_CHECK_COMMANDS:
        raise ValueError(f"unknown remote check: {check!r}; allowed: {sorted(REMOTE_CHECK_COMMANDS)}")
    timeout, identity = _validate_ssh_options(timeout, identity_file)
    remote_command = REMOTE_CHECK_COMMANDS[check](*args)
    argv = _ssh_argv(target, remote_command, timeout=timeout, identity_file=identity)
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=timeout + 10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise RemoteCheckError(f"ssh execution failed for {target.label()}: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip().splitlines()
        hint = f": {detail[0][:200]}" if detail else ""
        raise RemoteCheckError(f"remote check {check!r} on {target.label()} failed (exit {completed.returncode}){hint}")
    return completed.stdout


def parse_remote_disk(output: str, path: str) -> dict[str, float | str]:
    """Parse ``df -kP`` output into disk capacity fields."""
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        raise RemoteCheckError(f"unexpected df output for remote path {path!r}")
    fields = lines[1].split()
    if len(fields) < 6:
        raise RemoteCheckError(f"unexpected df output for remote path {path!r}")
    try:
        total_kb = int(fields[1])
        used_kb = int(fields[2])
        available_kb = int(fields[3])
        used_percent = float(fields[4].rstrip("%"))
    except ValueError as exc:
        raise RemoteCheckError(f"could not parse df output for remote path {path!r}") from exc
    total_bytes = total_kb * 1024
    return {
        "path": path,
        "total_bytes": total_bytes,
        "used_bytes": used_kb * 1024,
        "free_bytes": available_kb * 1024,
        "used_percent": round(used_percent, 2),
    }


def parse_remote_environment(output: str) -> dict[str, str | int | None]:
    """Parse the compound environment probe into host descriptor fields."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 5:
        raise RemoteCheckError("unexpected remote environment output")
    hostname, kernel_name, kernel_release, architecture, cpu_raw = lines[:5]
    cpu_count: int | None = None
    if cpu_raw.isdigit():
        cpu_count = int(cpu_raw)
    return {
        "hostname": hostname,
        "platform": kernel_name or "unknown",
        "platform_release": kernel_release or "unknown",
        "architecture": architecture or "unknown",
        "cpu_count": cpu_count,
    }


def parse_remote_memory(output: str) -> dict[str, int | float]:
    """Parse ``/proc/meminfo`` excerpt into memory capacity fields."""
    values: dict[str, int] = {}
    for line in output.splitlines():
        key, _, rest = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            digits = "".join(char for char in rest if char.isdigit())
            if digits:
                values[key] = int(digits) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise RemoteCheckError("unexpected remote meminfo output")
    total = values["MemTotal"]
    available = max(0, min(values["MemAvailable"], total))
    used = total - available
    return {
        "total_bytes": total,
        "available_bytes": available,
        "used_bytes": used,
        "used_percent": round(used / total * 100.0, 2) if total else 0.0,
    }


def remote_disk_status(
    target: SshTarget,
    path: str = "/",
    *,
    timeout: float = _SSH_TIMEOUT_SECONDS,
    identity_file: str | None = None,
) -> dict[str, float | str]:
    """Collect disk capacity from a remote host (read-only, over SSH)."""
    return parse_remote_disk(run_remote_check(target, "disk", path, timeout=timeout, identity_file=identity_file), path)


def remote_environment_status(
    target: SshTarget,
    *,
    timeout: float = _SSH_TIMEOUT_SECONDS,
    identity_file: str | None = None,
) -> dict[str, str | int | None]:
    """Collect a host descriptor from a remote host (read-only, over SSH)."""
    return parse_remote_environment(
        run_remote_check(target, "environment", timeout=timeout, identity_file=identity_file)
    )


def remote_memory_status(
    target: SshTarget,
    *,
    timeout: float = _SSH_TIMEOUT_SECONDS,
    identity_file: str | None = None,
) -> dict[str, int | float]:
    """Collect memory pressure from a remote Linux host (read-only, over SSH)."""
    return parse_remote_memory(run_remote_check(target, "memory", timeout=timeout, identity_file=identity_file))


def remote_check_operation(
    target: SshTarget,
    check: str,
    *args: str,
    timeout: float = _SSH_TIMEOUT_SECONDS,
    identity_file: str | None = None,
) -> Operation:
    """Wrap a remote check as a non-mutating :class:`Operation` for fleet workflows.

    The operation name embeds the target label so audit events stay
    attributable when one workflow fans out across many hosts.
    """
    collectors: dict[str, Callable[[], dict[str, Any]]] = {
        "disk": lambda: remote_disk_status(target, *args, timeout=timeout, identity_file=identity_file),
        "environment": lambda: remote_environment_status(target, timeout=timeout, identity_file=identity_file),
        "memory": lambda: remote_memory_status(target, timeout=timeout, identity_file=identity_file),
    }
    try:
        collector = collectors[check]
    except KeyError:
        raise ValueError(f"unknown remote check: {check!r}; allowed: {sorted(REMOTE_CHECK_COMMANDS)}") from None
    return Operation(f"remote-{check}@{target.label()}", collector, mutates_state=False)
