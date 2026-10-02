"""CLI tests for the new check commands, remote preflight, and watch."""

import csv
import io
import json

from autoops import checks
from autoops import cli as cli_module
from autoops.cli import REMOTE_PREFLIGHT_SCHEMA_VERSION, build_parser, main

# --- memory ---------------------------------------------------------------------


def test_memory_cli_json(capsys) -> None:
    assert main(["memory", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] in {"ok", "warning"}
    assert payload["total_bytes"] > 0
    assert 0 <= payload["used_percent"] <= 100


def test_memory_cli_csv(capsys) -> None:
    assert main(["memory", "--csv"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert rows[0]["state"] in {"ok", "warning"}


def test_memory_fail_on_warning(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"memory_warning_percent": 0}', encoding="utf-8")
    result = main(["--config", str(config), "memory", "--json", "--fail-on-warning"])
    captured = capsys.readouterr()
    assert result == 1
    assert json.loads(captured.out)["state"] == "warning"
    config.write_text('{"memory_warning_percent": 100}', encoding="utf-8")
    assert main(["--config", str(config), "memory", "--fail-on-warning"]) == 0


def test_memory_cli_rejects_bad_config(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"memory_warning_percent": 101}', encoding="utf-8")
    assert main(["--config", str(config), "memory"]) == 2
    assert "memory_warning_percent" in capsys.readouterr().err


# --- systemd ----------------------------------------------------------------------


class _Completed:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def _fake_systemctl(monkeypatch, stdout: str) -> None:
    monkeypatch.setattr(checks.subprocess, "run", lambda *a, **k: _Completed(stdout))


def test_systemd_cli_json(monkeypatch, capsys) -> None:
    _fake_systemctl(monkeypatch, "ActiveState=active\nSubState=running\nLoadState=loaded\n")
    assert main(["systemd", "ssh.service", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unit"] == "ssh.service"
    assert payload["state"] == "active"


def test_systemd_cli_fail_on_warning(monkeypatch, capsys) -> None:
    _fake_systemctl(monkeypatch, "ActiveState=failed\nSubState=failed\nLoadState=loaded\n")
    assert main(["systemd", "ssh.service", "--fail-on-warning"]) == 1
    assert main(["systemd", "ssh.service"]) == 0


def test_systemd_cli_rejects_bad_unit(capsys) -> None:
    assert main(["systemd", "evil;id"]) == 2
    captured = capsys.readouterr()
    assert "unit" in captured.err
    assert captured.out == ""


# --- tls -----------------------------------------------------------------------------


class _FakeTlsSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getpeercert(self, binary_form: bool = False):
        # Minimal DER certificate expiring 2030-01-01 (built in test_extended_checks).
        from tests.test_extended_checks import _synthetic_cert

        return _synthetic_cert(b"300101000000Z")


class _FakeContext:
    def __init__(self, *args, **kwargs) -> None:
        self.check_hostname = True
        self.verify_mode = None

    def wrap_socket(self, raw, server_hostname=None):
        return _FakeTlsSocket()


def _fake_tls(monkeypatch) -> None:
    monkeypatch.setattr(checks.socket, "create_connection", lambda *a, **k: object())
    monkeypatch.setattr(checks.ssl, "SSLContext", _FakeContext)


def test_tls_cli_json(monkeypatch, capsys) -> None:
    _fake_tls(monkeypatch)
    assert main(["tls", "example.com", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["host"] == "example.com"
    assert payload["port"] == 443
    assert payload["not_after"] == "2030-01-01T00:00:00Z"
    assert payload["state"] == "ok"


def test_tls_cli_fail_on_warning(monkeypatch, capsys) -> None:
    _fake_tls(monkeypatch)
    assert main(["tls", "example.com", "--warning-days", "100000", "--fail-on-warning"]) == 1
    assert main(["tls", "example.com", "--fail-on-warning"]) == 0


def test_tls_cli_rejects_bad_host(capsys) -> None:
    assert main(["tls", "https://example.com"]) == 2
    captured = capsys.readouterr()
    assert "host" in captured.err
    assert captured.out == ""


# --- loggrowth --------------------------------------------------------------------------


def test_loggrowth_cli_json(tmp_path, capsys) -> None:
    target = tmp_path / "app.log"
    target.write_text("hello\n", encoding="utf-8")
    assert main(["loggrowth", str(target), "--interval-seconds", "0.01", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "ok"
    assert payload["growth_bytes"] == 0


def test_loggrowth_cli_fail_on_warning(monkeypatch, tmp_path, capsys) -> None:
    target = tmp_path / "app.log"
    target.write_text("x", encoding="utf-8")
    sizes = iter([100, 10100])
    monkeypatch.setattr(checks, "_regular_file_size", lambda path: next(sizes))
    result = main(
        [
            "loggrowth",
            str(target),
            "--interval-seconds",
            "1",
            "--max-bytes-per-second",
            "100",
            "--json",
            "--fail-on-warning",
        ]
    )
    assert result == 1
    assert json.loads(capsys.readouterr().out)["state"] == "warning"


def test_loggrowth_cli_missing_file(capsys, tmp_path) -> None:
    assert main(["loggrowth", str(tmp_path / "missing.log")]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


# --- remote preflight ----------------------------------------------------------------------


def _fake_remote(monkeypatch) -> None:
    monkeypatch.setattr(
        cli_module,
        "remote_environment_status",
        lambda target, **kwargs: {
            "hostname": "web-01",
            "platform": "Linux",
            "platform_release": "6.8.0",
            "architecture": "x86_64",
            "cpu_count": 4,
        },
    )
    monkeypatch.setattr(
        cli_module,
        "remote_disk_status",
        lambda target, path="/", **kwargs: {
            "path": "/",
            "total_bytes": 100 * 1024**3,
            "used_bytes": 95 * 1024**3,
            "free_bytes": 5 * 1024**3,
            "used_percent": 95.0,
        },
    )
    monkeypatch.setattr(
        cli_module,
        "remote_memory_status",
        lambda target, **kwargs: {
            "total_bytes": 16 * 1024**3,
            "available_bytes": 8 * 1024**3,
            "used_bytes": 8 * 1024**3,
            "used_percent": 50.0,
        },
    )


def test_remote_preflight_json(monkeypatch, capsys) -> None:
    _fake_remote(monkeypatch)
    assert main(["preflight", "ssh://deploy@web-01:2222", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == REMOTE_PREFLIGHT_SCHEMA_VERSION == 5
    assert payload["remote_host"] == "deploy@web-01:2222"
    assert payload["hostname"] == "web-01"
    assert payload["disk_used_percent"] == 95.0
    assert payload["disk_state"] == "warning"
    assert payload["memory_used_percent"] == 50.0
    assert payload["memory_state"] == "ok"
    assert payload["overall_state"] == "warning"
    assert payload["python_version"] is None


def test_remote_preflight_fail_on_warning(monkeypatch, capsys) -> None:
    _fake_remote(monkeypatch)
    result = main(["preflight", "ssh://web-01", "--json", "--fail-on-warning"])
    assert result == 1
    assert json.loads(capsys.readouterr().out)["overall_state"] == "warning"


def test_remote_preflight_rejects_bad_target(capsys) -> None:
    assert main(["preflight", "ssh://-oProxyCommand=evil"]) == 2
    captured = capsys.readouterr()
    assert "error:" in captured.err
    assert captured.out == ""


def test_remote_preflight_csv_schema(monkeypatch, capsys) -> None:
    _fake_remote(monkeypatch)
    assert main(["preflight", "ssh://web-01", "--csv"]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert rows[0]["schema_version"] == "5"
    assert rows[0]["remote_host"] == "web-01"
    assert rows[0]["memory_state"] == "ok"


# --- watch -------------------------------------------------------------------------------


def test_watch_cli_runs_bounded(tmp_path, capsys) -> None:
    sink_path = tmp_path / "audit.ndjson"
    result = main(
        [
            "watch",
            "--sink",
            f"file:{sink_path}",
            "--checks",
            "disk,environment",
            "--runs",
            "1",
            "--interval-seconds",
            "60",
            "--path",
            str(tmp_path),
        ]
    )
    assert result == 0
    lines = sink_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    events = [json.loads(line) for line in lines]
    assert {event["data"]["operation"] for event in events} == {"watch-disk", "watch-environment"}
    assert all(event["event"] == "operation_result" for event in events)
    captured = capsys.readouterr()
    assert "iteration 1" in captured.err
    assert captured.out == ""


def test_watch_cli_rejects_unknown_check(tmp_path, capsys) -> None:
    result = main(["watch", "--sink", f"file:{tmp_path}/a.ndjson", "--checks", "nmap", "--runs", "1"])
    assert result == 2
    captured = capsys.readouterr()
    assert "unknown watch check" in captured.err
    assert captured.out == ""


def test_watch_cli_rejects_bad_sink(tmp_path, capsys) -> None:
    result = main(["watch", "--sink", "ftp://example.com/x", "--runs", "1"])
    assert result == 2
    assert "error:" in capsys.readouterr().err


def test_watch_cli_verbose_flag_parses(tmp_path) -> None:
    args = build_parser().parse_args(
        ["--verbose", "watch", "--sink", f"file:{tmp_path}/a.ndjson", "--runs", "1", "--interval-seconds", "60"]
    )
    assert args.verbose is True
    assert args.command == "watch"


def test_global_verbose_flag_defaults_off() -> None:
    args = build_parser().parse_args(["disk", "."])
    assert args.verbose is False
