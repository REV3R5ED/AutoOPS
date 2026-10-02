"""Read-only system health checks used by AutoOPS."""

from __future__ import annotations

import os
import platform
import re
import shutil
import socket
import ssl
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from autoops.config import DEFAULT_MEMORY_WARNING_PERCENT


@dataclass(frozen=True)
class DiskStatus:
    """A serializable snapshot of filesystem capacity."""

    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    used_percent: float

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class EnvironmentStatus:
    """A read-only, cross-platform snapshot useful for operational preflight checks."""

    hostname: str
    platform: str
    platform_release: str
    architecture: str
    python_version: str
    cpu_count: int | None

    def to_dict(self) -> dict[str, str | int | None]:
        return asdict(self)


@dataclass(frozen=True)
class FileFreshnessStatus:
    """A serializable snapshot describing how recently a file was modified."""

    path: str
    size_bytes: int
    modified_at: str
    age_seconds: float
    max_age_seconds: float
    state: str

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class MemoryStatus:
    """A serializable snapshot of host memory pressure."""

    total_bytes: int
    available_bytes: int
    used_bytes: int
    used_percent: float
    warning_percent: float
    state: str  # "ok" or "warning"

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class SystemdServiceStatus:
    """A serializable snapshot of one systemd unit's health."""

    unit: str
    active_state: str | None
    sub_state: str | None
    load_state: str | None
    state: str  # "active", "inactive", "failed", "not-found", or "unknown"

    def to_dict(self) -> dict[str, str | None]:
        return asdict(self)


@dataclass(frozen=True)
class TlsCertificateStatus:
    """A serializable snapshot of a remote TLS certificate's expiry."""

    host: str
    port: int
    not_after: str
    days_remaining: float
    warning_days: float
    state: str  # "ok", "warning", or "expired"

    def to_dict(self) -> dict[str, str | int | float]:
        return asdict(self)


@dataclass(frozen=True)
class LogGrowthStatus:
    """A serializable snapshot of a log file's short-term growth rate."""

    path: str
    size_bytes: int
    previous_size_bytes: int
    interval_seconds: float
    growth_bytes: int
    growth_bytes_per_second: float
    max_bytes_per_second: float | None
    state: str  # "ok", "warning", or "rotated"

    def to_dict(self) -> dict[str, str | int | float | None]:
        return asdict(self)


def disk_status(path: str = ".") -> DiskStatus:
    """Return a read-only disk usage snapshot for *path*.

    Raises FileNotFoundError when the requested path does not exist.
    """
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")

    usage = shutil.disk_usage(target)
    used_percent = (usage.used / usage.total * 100.0) if usage.total else 0.0
    return DiskStatus(
        path=str(target.resolve()),
        total_bytes=usage.total,
        used_bytes=usage.used,
        free_bytes=usage.free,
        used_percent=round(used_percent, 2),
    )


def environment_status() -> EnvironmentStatus:
    """Return a read-only runtime/host snapshot without probing the network."""
    return EnvironmentStatus(
        hostname=socket.gethostname(),
        platform=platform.system() or "unknown",
        platform_release=platform.release() or "unknown",
        architecture=platform.machine() or "unknown",
        python_version=platform.python_version() or sys.version.split()[0],
        cpu_count=os.cpu_count(),
    )


def file_freshness(path: str, max_age_seconds: float, *, now: datetime | None = None) -> FileFreshnessStatus:
    """Return a read-only freshness assessment for a regular file.

    This is useful for checking whether backups, exports, logs, or other expected
    artifacts are still being produced. Directories are rejected to keep the
    contract unambiguous. ``max_age_seconds`` must be finite and non-negative.
    Modification times more than one second later than the reference clock are
    reported as ``future``. The small tolerance avoids false anomalies caused by
    filesystem timestamp/clock resolution differences across operating systems.
    """
    if not isinstance(max_age_seconds, (int, float)) or isinstance(max_age_seconds, bool):
        raise ValueError("max_age_seconds must be a finite non-negative number")
    if not (0 <= float(max_age_seconds) < float("inf")):
        raise ValueError("max_age_seconds must be a finite non-negative number")

    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    if not target.is_file():
        raise ValueError(f"Path is not a regular file: {target}")

    stat = target.stat()
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
    raw_age_seconds = (current.astimezone(timezone.utc) - modified).total_seconds()
    age_seconds = max(0.0, raw_age_seconds)
    threshold = float(max_age_seconds)
    if raw_age_seconds < -1.0:
        state = "future"
    elif raw_age_seconds > threshold:
        state = "stale"
    else:
        state = "ok"
    return FileFreshnessStatus(
        path=str(target.resolve()),
        size_bytes=stat.st_size,
        modified_at=modified.isoformat().replace("+00:00", "Z"),
        age_seconds=round(age_seconds, 3),
        max_age_seconds=threshold,
        state=state,
    )


def _validate_percent(value: float, name: str) -> float:
    """Validate a 0-100 warning threshold shared by capacity-style checks."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    threshold = float(value)
    if not (0 <= threshold <= 100):
        raise ValueError(f"{name} must be between 0 and 100")
    return threshold


def _linux_memory_bytes() -> tuple[int, int] | None:
    """Return (total, available) bytes from /proc/meminfo, or None if unreadable."""
    try:
        text = Path("/proc/meminfo").read_text(encoding="utf-8")
    except OSError:
        return None
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in {"MemTotal", "MemAvailable"}:
            digits = "".join(char for char in rest if char.isdigit())
            if digits:
                values[key] = int(digits) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        return None
    return values["MemTotal"], values["MemAvailable"]


def _macos_memory_bytes() -> tuple[int, int] | None:
    """Return (total, available) bytes on macOS, or None if unreadable."""
    try:
        total_raw = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=10)
        page_raw = subprocess.run(["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, timeout=10)
        vm_stat = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if total_raw.returncode != 0 or vm_stat.returncode != 0:
        return None
    try:
        total = int(total_raw.stdout.strip())
        page_size = int(page_raw.stdout.strip()) if page_raw.returncode == 0 else 4096
    except ValueError:
        return None
    free_pages = 0
    for line in vm_stat.stdout.splitlines():
        # vm_stat lines look like "Pages free: 12345."
        name, _, rest = line.partition(":")
        if name.strip() in {"Pages free", "Pages inactive", "Pages speculative"}:
            digits = "".join(char for char in rest if char.isdigit())
            if digits:
                free_pages += int(digits)
    if free_pages <= 0:
        return None
    available = free_pages * page_size
    return total, min(available, total)


def _windows_memory_bytes() -> tuple[int, int] | None:
    """Return (total, available) bytes on Windows, or None if unreadable."""
    try:
        import ctypes

        class MemoryStatusEx(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatusEx()
        status.dwLength = ctypes.sizeof(MemoryStatusEx)
        windll = getattr(ctypes, "windll", None)
        if windll is None:
            return None
        if not windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return None
        return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except (OSError, AttributeError, ValueError):
        return None


def memory_status(warning_percent: float = DEFAULT_MEMORY_WARNING_PERCENT) -> MemoryStatus:
    """Return a read-only snapshot of host memory pressure.

    ``warning_percent`` is the used-memory percentage that flips the state to
    ``warning``. Raises OSError when memory information cannot be read on the
    current platform.
    """
    threshold = _validate_percent(warning_percent, "warning_percent")

    reader = {
        "Linux": _linux_memory_bytes,
        "Darwin": _macos_memory_bytes,
        "Windows": _windows_memory_bytes,
    }.get(platform.system())
    sample = reader() if reader is not None else None
    if sample is None:
        raise OSError("memory information is not available on this platform")
    total, available = sample
    if total <= 0:
        raise OSError("memory information is not available on this platform")
    available = max(0, min(available, total))
    used = total - available
    used_percent = round(used / total * 100.0, 2)
    return MemoryStatus(
        total_bytes=total,
        available_bytes=available,
        used_bytes=used,
        used_percent=used_percent,
        warning_percent=threshold,
        state="warning" if used_percent >= threshold else "ok",
    )


_UNIT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9@:._-]+$")
_SYSTEMCTL_TIMEOUT_SECONDS = 10


def systemd_service_status(unit: str) -> SystemdServiceStatus:
    """Return a read-only health snapshot for one systemd unit.

    The unit name is validated strictly and passed to ``systemctl`` as a
    single argv element (never through a shell). Raises ValueError for
    malformed unit names and OSError when ``systemctl`` is unavailable or
    the host is not running systemd.
    """
    if not isinstance(unit, str) or not unit:
        raise ValueError("unit must be a non-empty string")
    if any(ord(char) < 32 or ord(char) == 127 for char in unit):
        raise ValueError("unit must not contain control characters")
    if unit.startswith("-") or unit.startswith(".") or ".." in unit or "/" in unit:
        raise ValueError(f"unit is not a valid systemd unit name: {unit!r}")
    if not _UNIT_NAME_PATTERN.match(unit):
        raise ValueError(f"unit is not a valid systemd unit name: {unit!r}")

    try:
        completed = subprocess.run(
            ["systemctl", "show", "--no-pager", "-p", "ActiveState,SubState,LoadState", unit],
            capture_output=True,
            text=True,
            timeout=_SYSTEMCTL_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise OSError("systemctl is not available on this host") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError(f"could not query systemd unit {unit!r}: {exc}") from exc

    properties: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        key, _, value = line.partition("=")
        if key in {"ActiveState", "SubState", "LoadState"}:
            properties[key] = value.strip()

    if not properties:
        raise OSError(f"systemd did not return unit properties for {unit!r}; is systemd running?")

    active_state = properties.get("ActiveState")
    sub_state = properties.get("SubState")
    load_state = properties.get("LoadState")
    if load_state == "not-found":
        state = "not-found"
    elif active_state == "active":
        state = "active"
    elif active_state == "failed":
        state = "failed"
    elif active_state == "inactive":
        state = "inactive"
    else:
        state = "unknown"
    return SystemdServiceStatus(
        unit=unit,
        active_state=active_state,
        sub_state=sub_state,
        load_state=load_state,
        state=state,
    )


def _parse_der_not_after(der: bytes) -> str:
    """Extract the notAfter time string (e.g. ``"260101000000Z"``) from a DER certificate.

    Walks the outer Certificate and TBSCertificate sequences to the validity
    field without a full ASN.1 parser; only the lengths needed to reach the
    notAfter value are decoded.
    """

    def read_tlv(data: bytes, offset: int) -> tuple[int, bytes, int]:
        if offset + 2 > len(data):
            raise ValueError("truncated certificate")
        tag = data[offset]
        length_byte = data[offset + 1]
        if length_byte & 0x80:
            count = length_byte & 0x7F
            if count == 0 or offset + 2 + count > len(data):
                raise ValueError("invalid certificate length")
            length = int.from_bytes(data[offset + 2 : offset + 2 + count], "big")
            start = offset + 2 + count
        else:
            length = length_byte
            start = offset + 2
        end = start + length
        if end > len(data):
            raise ValueError("truncated certificate")
        return tag, data[start:end], end

    def expect_sequence(data: bytes, offset: int) -> tuple[bytes, int]:
        tag, value, end = read_tlv(data, offset)
        if tag != 0x30:
            raise ValueError("expected SEQUENCE in certificate")
        return value, end

    def skip(data: bytes, offset: int) -> int:
        _, _, end = read_tlv(data, offset)
        return end

    certificate, _ = expect_sequence(der, 0)
    tbs, _ = expect_sequence(certificate, 0)
    offset = 0
    # Optional [0] EXPLICIT version.
    if offset < len(tbs) and tbs[offset] == 0xA0:
        offset = skip(tbs, offset)
    offset = skip(tbs, offset)  # serialNumber
    offset = skip(tbs, offset)  # signature algorithm
    offset = skip(tbs, offset)  # issuer
    validity, _ = expect_sequence(tbs, offset)
    tag_before, _, middle = read_tlv(validity, 0)
    if tag_before not in {0x17, 0x18}:
        raise ValueError("expected notBefore time in certificate")
    tag, not_after, _ = read_tlv(validity, middle)
    if tag not in {0x17, 0x18}:
        raise ValueError("expected notAfter time in certificate")
    try:
        return not_after.decode("ascii")
    except UnicodeDecodeError as exc:
        raise ValueError("invalid notAfter encoding in certificate") from exc


def _parse_cert_time(value: str) -> datetime:
    """Parse a DER UTCTime/GeneralizedTime string into a UTC datetime."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1]
    if len(text) == 12:  # UTCTime YYMMDDHHMMSS
        year = int(text[0:2])
        year += 2000 if year < 50 else 1900
        text = f"{year:04d}" + text[2:]
    parsed = datetime.strptime(text, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    return parsed


def _validate_tls_host(host: str) -> str:
    if not isinstance(host, str) or not host.strip():
        raise ValueError("host must be a non-empty string")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in host):
        raise ValueError("host must not contain whitespace or control characters")
    if "://" in host or "/" in host:
        raise ValueError("host must be a bare hostname or IP address, not a URL")
    return host.strip()


def _validate_tls_port(port: int) -> int:
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port must be an integer")
    if not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


def tls_certificate_status(
    host: str,
    port: int = 443,
    *,
    warning_days: float = 30.0,
    timeout: float = 10.0,
    now: datetime | None = None,
) -> TlsCertificateStatus:
    """Return a read-only expiry assessment for a remote TLS certificate.

    Opens a TCP connection, performs a TLS handshake, and reads the leaf
    certificate's expiry. Certificate chain validation is intentionally
    disabled: this check measures expiry only and must not fail closed on
    trust configuration. Raises ValueError for invalid arguments and OSError
    for connection or handshake failures.
    """
    target_host = _validate_tls_host(host)
    target_port = _validate_tls_port(port)
    if isinstance(warning_days, bool) or not isinstance(warning_days, (int, float)):
        raise ValueError("warning_days must be a number")
    warning_days = float(warning_days)
    if not (0 <= warning_days < float("inf")):
        raise ValueError("warning_days must be a finite non-negative number")
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a number")
    timeout = float(timeout)
    if not (0 < timeout < float("inf")):
        raise ValueError("timeout must be a finite positive number")
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        raw = socket.create_connection((target_host, target_port), timeout=timeout)
    except OSError as exc:
        raise OSError(f"could not connect to {target_host}:{target_port}: {exc}") from exc
    try:
        with context.wrap_socket(raw, server_hostname=target_host) as tls:
            der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError) as exc:
        raise OSError(f"TLS handshake with {target_host}:{target_port} failed: {exc}") from exc
    if not der:
        raise OSError(f"no certificate presented by {target_host}:{target_port}")

    try:
        not_after = _parse_cert_time(_parse_der_not_after(der))
    except ValueError as exc:
        raise OSError(f"could not parse certificate from {target_host}:{target_port}: {exc}") from exc

    days_remaining = (not_after - current).total_seconds() / 86400.0
    if days_remaining < 0:
        state = "expired"
    elif days_remaining <= warning_days:
        state = "warning"
    else:
        state = "ok"
    return TlsCertificateStatus(
        host=target_host,
        port=target_port,
        not_after=not_after.isoformat().replace("+00:00", "Z"),
        days_remaining=round(days_remaining, 3),
        warning_days=warning_days,
        state=state,
    )


def _regular_file_size(path: str) -> int:
    target = Path(path).expanduser()
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {target}")
    if not target.is_file():
        raise ValueError(f"Path is not a regular file: {target}")
    return target.stat().st_size


def log_growth_status(
    path: str,
    *,
    interval_seconds: float = 1.0,
    max_bytes_per_second: float | None = None,
    sleep: Callable[[float], None] | None = None,
) -> LogGrowthStatus:
    """Return a read-only assessment of a log file's short-term growth rate.

    Samples the file size twice separated by ``interval_seconds`` and reports
    the growth rate. A shrinking file is reported as ``rotated`` (log
    rotation or truncation) rather than healthy growth. When
    ``max_bytes_per_second`` is set, a faster growth rate flips the state to
    ``warning``. The check only reads file metadata.
    """
    if isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float)):
        raise ValueError("interval_seconds must be a number")
    interval = float(interval_seconds)
    if not (0 < interval < float("inf")):
        raise ValueError("interval_seconds must be a finite positive number")
    if max_bytes_per_second is not None:
        if isinstance(max_bytes_per_second, bool) or not isinstance(max_bytes_per_second, (int, float)):
            raise ValueError("max_bytes_per_second must be a number or null")
        max_bytes_per_second = float(max_bytes_per_second)
        if not (0 <= max_bytes_per_second < float("inf")):
            raise ValueError("max_bytes_per_second must be a finite non-negative number")

    resolved = str(Path(path).expanduser().resolve())
    previous_size = _regular_file_size(path)
    (sleep or time.sleep)(interval)
    size = _regular_file_size(path)

    growth = size - previous_size
    growth_bps = growth / interval
    if growth < 0:
        state = "rotated"
    elif max_bytes_per_second is not None and growth_bps > max_bytes_per_second:
        state = "warning"
    else:
        state = "ok"
    return LogGrowthStatus(
        path=resolved,
        size_bytes=size,
        previous_size_bytes=previous_size,
        interval_seconds=interval,
        growth_bytes=growth,
        growth_bytes_per_second=round(growth_bps, 3),
        max_bytes_per_second=max_bytes_per_second,
        state=state,
    )
