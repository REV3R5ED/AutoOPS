"""Tests for the extended read-only checks: memory, systemd, TLS, log growth."""

from datetime import datetime, timezone

import pytest

from autoops import checks
from autoops.checks import (
    _parse_cert_time,
    _parse_der_not_after,
    log_growth_status,
    memory_status,
    systemd_service_status,
    tls_certificate_status,
)


def _tlv(tag: int, content: bytes) -> bytes:
    size = len(content)
    if size < 128:
        return bytes([tag, size]) + content
    length = size.to_bytes((size.bit_length() + 7) // 8, "big")
    return bytes([tag, 0x80 | len(length)]) + length + content


def _synthetic_cert(not_after: bytes) -> bytes:
    version = _tlv(0xA0, _tlv(0x02, b"\x02"))
    serial = _tlv(0x02, b"\x01")
    sigalg = _tlv(0x30, _tlv(0x06, bytes.fromhex("2a864886f70d01010b")) + _tlv(0x05, b""))
    issuer = _tlv(0x30, b"")
    validity = _tlv(0x30, _tlv(0x17, b"230101000000Z") + _tlv(0x17, not_after))
    subject = _tlv(0x30, b"")
    spki = _tlv(0x30, _tlv(0x30, b"") + _tlv(0x03, b"\x00"))
    tbs = _tlv(0x30, version + serial + sigalg + issuer + validity + subject + spki)
    return _tlv(0x30, tbs + sigalg + _tlv(0x03, b"\x00"))


# --- DER / certificate time parsing ----------------------------------------


def test_parse_der_not_after_utctime() -> None:
    assert _parse_der_not_after(_synthetic_cert(b"300101000000Z")) == "300101000000Z"


def test_parse_der_not_after_generalizedtime() -> None:
    assert _parse_der_not_after(_synthetic_cert(b"20490101000000Z")) == "20490101000000Z"


def test_parse_der_not_after_rejects_malformed() -> None:
    for bad in (b"", b"\x30\x00", b"\x30\x03\x01\x01\xff", b"\x04\x03abc", _synthetic_cert(b"300101000000Z")[:20]):
        with pytest.raises(ValueError):
            _parse_der_not_after(bad)


def test_parse_cert_time_utctime_year_pivot() -> None:
    assert _parse_cert_time("490101000000Z").year == 2049
    assert _parse_cert_time("500101000000Z").year == 1950
    assert _parse_cert_time("20490101000000Z").year == 2049


# --- memory -----------------------------------------------------------------


def test_memory_status_linux_warning(monkeypatch) -> None:
    monkeypatch.setattr(checks.platform, "system", lambda: "Linux")
    monkeypatch.setattr(checks, "_linux_memory_bytes", lambda: (8 * 1024**3, 1 * 1024**3))
    status = memory_status(warning_percent=80.0)
    assert status.total_bytes == 8 * 1024**3
    assert status.available_bytes == 1 * 1024**3
    assert status.used_bytes == 7 * 1024**3
    assert status.used_percent == 87.5
    assert status.state == "warning"
    payload = status.to_dict()
    assert payload["state"] == "warning"


def test_memory_status_healthy(monkeypatch) -> None:
    monkeypatch.setattr(checks.platform, "system", lambda: "Linux")
    monkeypatch.setattr(checks, "_linux_memory_bytes", lambda: (8 * 1024**3, 7 * 1024**3))
    status = memory_status()
    assert status.used_percent == 12.5
    assert status.state == "ok"
    assert status.warning_percent == 90.0


def test_memory_status_rejects_bad_threshold() -> None:
    for bad in (True, "90", float("nan"), -1, 101):
        with pytest.raises(ValueError):
            memory_status(warning_percent=bad)


def test_memory_status_unsupported_platform(monkeypatch) -> None:
    monkeypatch.setattr(checks.platform, "system", lambda: "Plan9")
    with pytest.raises(OSError, match="not available"):
        memory_status()


def test_memory_status_unreadable_meminfo(monkeypatch) -> None:
    monkeypatch.setattr(checks.platform, "system", lambda: "Linux")
    monkeypatch.setattr(checks, "_linux_memory_bytes", lambda: None)
    with pytest.raises(OSError, match="not available"):
        memory_status()


def test_linux_memory_reader_parses_meminfo(monkeypatch) -> None:
    class FakePath:
        def __init__(self, *args) -> None:
            pass

        def read_text(self, encoding: str = "utf-8") -> str:
            return "MemTotal:        8192 kB\nMemAvailable:    2048 kB\nSwapTotal: 0 kB\n"

    monkeypatch.setattr(checks, "Path", FakePath)
    assert checks._linux_memory_bytes() == (8192 * 1024, 2048 * 1024)


# --- systemd -----------------------------------------------------------------


class _Completed:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def _systemctl_ok(stdout: str):
    def fake(*args, **kwargs):
        assert args[0][0] == "systemctl"
        assert args[0][-1] == "ssh.service"
        return _Completed(stdout)

    return fake


def test_systemd_active_unit(monkeypatch) -> None:
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        _systemctl_ok("ActiveState=active\nSubState=running\nLoadState=loaded\n"),
    )
    status = systemd_service_status("ssh.service")
    assert status.unit == "ssh.service"
    assert status.active_state == "active"
    assert status.sub_state == "running"
    assert status.load_state == "loaded"
    assert status.state == "active"


def test_systemd_failed_unit(monkeypatch) -> None:
    monkeypatch.setattr(
        checks.subprocess,
        "run",
        _systemctl_ok("ActiveState=failed\nSubState=failed\nLoadState=loaded\n"),
    )
    assert systemd_service_status("ssh.service").state == "failed"


def test_systemd_not_found_unit(monkeypatch) -> None:
    def fake(*args, **kwargs):
        return _Completed("LoadState=not-found\nActiveState=inactive\nSubState=dead\n", returncode=4)

    monkeypatch.setattr(checks.subprocess, "run", fake)
    status = systemd_service_status("nope.service")
    assert status.state == "not-found"


def test_systemd_rejects_malicious_unit_names() -> None:
    for bad in ("", "ssh; rm -rf /", "../x", "/bin/sh", "-h", "a b", "unit\x00", "ünïcodé.service!"):
        with pytest.raises(ValueError):
            systemd_service_status(bad)


def test_systemd_rejects_non_string_unit() -> None:
    with pytest.raises(ValueError):
        systemd_service_status(None)


def test_systemd_missing_systemctl(monkeypatch) -> None:
    def fake(*args, **kwargs):
        raise FileNotFoundError("no systemctl")

    monkeypatch.setattr(checks.subprocess, "run", fake)
    with pytest.raises(OSError, match="systemctl is not available"):
        systemd_service_status("ssh.service")


def test_systemd_empty_output_is_operational_error(monkeypatch) -> None:
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: _Completed(""))
    with pytest.raises(OSError, match="systemd"):
        systemd_service_status("ssh.service")


# --- TLS ---------------------------------------------------------------------


class _FakeTlsSocket:
    def __init__(self, der: bytes) -> None:
        self._der = der

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getpeercert(self, binary_form: bool = False):
        assert binary_form
        return self._der


class _FakeContext:
    der = _synthetic_cert(b"300101000000Z")

    def __init__(self, *args, **kwargs) -> None:
        self.check_hostname = True
        self.verify_mode = None

    def wrap_socket(self, raw, server_hostname=None):
        assert self.check_hostname is False
        return _FakeTlsSocket(self.der)


def _patch_tls(monkeypatch, der: bytes) -> None:
    _FakeContext.der = der
    monkeypatch.setattr(checks.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(checks.ssl, "SSLContext", _FakeContext)


def test_tls_certificate_ok(monkeypatch) -> None:
    _patch_tls(monkeypatch, _synthetic_cert(b"300101000000Z"))
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    status = tls_certificate_status("example.com", 443, warning_days=30, now=now)
    assert status.host == "example.com"
    assert status.port == 443
    assert status.not_after == "2030-01-01T00:00:00Z"
    assert status.days_remaining == pytest.approx(1461.0)
    assert status.state == "ok"


def test_tls_certificate_warning_and_expired(monkeypatch) -> None:
    _patch_tls(monkeypatch, _synthetic_cert(b"260101000000Z"))
    soon = datetime(2025, 12, 20, tzinfo=timezone.utc)
    assert tls_certificate_status("example.com", now=soon, warning_days=30).state == "warning"
    late = datetime(2026, 2, 1, tzinfo=timezone.utc)
    expired = tls_certificate_status("example.com", now=late, warning_days=30)
    assert expired.state == "expired"
    assert expired.days_remaining < 0


def test_tls_rejects_bad_input() -> None:
    with pytest.raises(ValueError):
        tls_certificate_status("")
    with pytest.raises(ValueError):
        tls_certificate_status("https://example.com")
    with pytest.raises(ValueError):
        tls_certificate_status("exa mple.com")
    with pytest.raises(ValueError):
        tls_certificate_status("example.com", 0)
    with pytest.raises(ValueError):
        tls_certificate_status("example.com", 70000)
    with pytest.raises(ValueError):
        tls_certificate_status("example.com", True)
    with pytest.raises(ValueError):
        tls_certificate_status("example.com", warning_days=-1)
    with pytest.raises(ValueError):
        tls_certificate_status("example.com", timeout=0)


def test_tls_connection_failure_is_operational_error(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(checks.socket, "create_connection", fail)
    with pytest.raises(OSError, match="could not connect"):
        tls_certificate_status("example.com")


def test_tls_unparseable_certificate_is_operational_error(monkeypatch) -> None:
    _patch_tls(monkeypatch, b"\x30\x03\x01\x01\xff")
    with pytest.raises(OSError, match="could not parse certificate"):
        tls_certificate_status("example.com")


# --- log growth ----------------------------------------------------------------


def test_log_growth_no_growth(tmp_path) -> None:
    target = tmp_path / "app.log"
    target.write_text("line\n", encoding="utf-8")
    status = log_growth_status(str(target), interval_seconds=0.01, sleep=lambda seconds: None)
    assert status.state == "ok"
    assert status.growth_bytes == 0
    assert status.growth_bytes_per_second == 0.0
    assert status.path == str(target.resolve())


def test_log_growth_warning(monkeypatch, tmp_path) -> None:
    target = tmp_path / "app.log"
    target.write_text("x", encoding="utf-8")
    sizes = iter([100, 100 + 5000])
    monkeypatch.setattr(checks, "_regular_file_size", lambda path: next(sizes))
    status = log_growth_status(
        str(target), interval_seconds=2.0, max_bytes_per_second=1000.0, sleep=lambda seconds: None
    )
    assert status.growth_bytes == 5000
    assert status.growth_bytes_per_second == 2500.0
    assert status.state == "warning"


def test_log_growth_rotated_when_shrinking(monkeypatch, tmp_path) -> None:
    target = tmp_path / "app.log"
    target.write_text("x", encoding="utf-8")
    sizes = iter([5000, 100])
    monkeypatch.setattr(checks, "_regular_file_size", lambda path: next(sizes))
    status = log_growth_status(str(target), interval_seconds=1.0, max_bytes_per_second=1.0, sleep=lambda seconds: None)
    assert status.state == "rotated"
    assert status.growth_bytes == -4900


def test_log_growth_rejects_bad_arguments(tmp_path) -> None:
    target = tmp_path / "app.log"
    target.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        log_growth_status(str(target), interval_seconds=0)
    with pytest.raises(ValueError):
        log_growth_status(str(target), interval_seconds=float("inf"))
    with pytest.raises(ValueError):
        log_growth_status(str(target), max_bytes_per_second=-1)
    with pytest.raises(FileNotFoundError):
        log_growth_status(str(tmp_path / "missing.log"))
    with pytest.raises(ValueError):
        log_growth_status(str(tmp_path))
