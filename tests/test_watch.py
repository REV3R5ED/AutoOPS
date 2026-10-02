"""Tests for autoops watch: sinks, event collection, and the watch loop."""

import json
import socket
from datetime import datetime, timezone

import pytest

from autoops import watch
from autoops.operations import Operation
from autoops.watch import (
    FileSink,
    HttpSink,
    SinkError,
    SyslogSink,
    collect_audit_events,
    parse_sink,
    run_watch,
)


def _ok_operation(name: str = "check") -> Operation:
    return Operation(name, lambda: {"detail": "fine"})


def _secret_operation() -> Operation:
    return Operation("secret-check", lambda: {"api_token": "hunter2", "nested": {"password": "x"}})


# --- sink parsing ---------------------------------------------------------------


def test_parse_file_sink(tmp_path) -> None:
    sink = parse_sink(f"file:{tmp_path}/audit.ndjson")
    assert isinstance(sink, FileSink)
    sink.close()


def test_parse_syslog_sink() -> None:
    sink = parse_sink("syslog")
    assert isinstance(sink, SyslogSink)
    sink.close()


def test_parse_syslog_with_address() -> None:
    if hasattr(socket, "AF_UNIX"):
        sink = parse_sink("syslog:/tmp/test-autoops-syslog.sock")
        assert isinstance(sink, SyslogSink)
        sink.close()
    else:
        with pytest.raises(SinkError, match="not supported on this platform"):
            parse_sink("syslog:/tmp/test-autoops-syslog.sock")
    sink = parse_sink("syslog:127.0.0.1:514")
    assert isinstance(sink, SyslogSink)
    sink.close()


def test_parse_http_sink() -> None:
    assert isinstance(parse_sink("http://localhost:8080/events"), HttpSink)
    assert isinstance(parse_sink("https://logs.example.com/ingest"), HttpSink)


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "file:",
        "ftp://example.com/x",
        "syslog:",
        "syslog:notahostport",
        "syslog:host:99999",
        "http://user:pass@example.com/",
        "http:///no-host",
    ],
)
def test_parse_sink_rejects_invalid_specs(spec: str) -> None:
    with pytest.raises(SinkError):
        parse_sink(spec)


def test_file_sink_missing_directory_is_sink_error(tmp_path) -> None:
    with pytest.raises(SinkError, match="could not open"):
        FileSink(tmp_path / "no-such-dir" / "audit.ndjson")


# --- file sink ---------------------------------------------------------------------


def test_file_sink_appends_ndjson(tmp_path) -> None:
    path = tmp_path / "audit.ndjson"
    sink = FileSink(path)
    event = {"event": "operation_result", "success": True, "data": {"a": 1}}
    sink.write_event(event)
    sink.write_event(event)
    sink.close()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == event


# --- http sink ------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_http_sink_posts_ndjson(monkeypatch) -> None:
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"] = request.full_url
        seen["method"] = request.get_method()
        seen["content_type"] = request.get_header("Content-type")
        seen["body"] = request.data
        seen["timeout"] = timeout
        return _FakeResponse(200)

    monkeypatch.setattr(watch.urllib.request, "urlopen", fake_urlopen)
    sink = HttpSink("https://logs.example.com/ingest")
    sink.write_event({"event": "operation_result"})
    assert seen["url"] == "https://logs.example.com/ingest"
    assert seen["method"] == "POST"
    assert seen["content_type"] == "application/x-ndjson"
    assert json.loads(seen["body"].decode("utf-8")) == {"event": "operation_result"}
    assert seen["timeout"] == 10.0


def test_http_sink_server_error_is_sink_error(monkeypatch) -> None:
    monkeypatch.setattr(watch.urllib.request, "urlopen", lambda *a, **k: _FakeResponse(500))
    with pytest.raises(SinkError, match="status 500"):
        HttpSink("https://logs.example.com/ingest").write_event({"event": "x"})


def test_http_sink_network_error_is_sink_error(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(watch.urllib.request, "urlopen", fail)
    with pytest.raises(SinkError, match="could not deliver"):
        HttpSink("https://logs.example.com/ingest").write_event({"event": "x"})


# --- event collection -------------------------------------------------------------------


def test_collect_audit_events_redacts_secrets() -> None:
    events = collect_audit_events(
        [_ok_operation(), _secret_operation()],
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    assert len(events) == 2
    assert all(event["event"] == "operation_result" for event in events)
    assert events[0]["timestamp"] == "2026-01-01T00:00:00Z"
    assert events[0]["data"]["detail"] == "fine"
    secret_event = events[1]
    assert secret_event["data"]["api_token"] == "[REDACTED]"
    assert secret_event["data"]["nested"]["password"] == "[REDACTED]"


def test_collect_audit_events_keeps_going_after_failure() -> None:
    failing = Operation("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom")))
    events = collect_audit_events([failing, _ok_operation()])
    assert len(events) == 2
    assert events[0]["success"] is False
    assert events[1]["success"] is True
    # suppressed by default
    assert "boom" not in events[0]["message"]


def test_collect_audit_events_verbose_reveals_detail() -> None:
    failing = Operation("bad", lambda: (_ for _ in ()).throw(RuntimeError("boom-secret")))
    events = collect_audit_events([failing], verbose=True)
    assert "boom-secret" in events[0]["message"]


def test_collect_audit_events_rejects_mutating_operations() -> None:
    mutating = Operation("change", lambda: {"changed": True}, mutates_state=True)
    with pytest.raises(ValueError, match="read-only"):
        collect_audit_events([mutating])


# --- watch loop ------------------------------------------------------------------------------


def test_run_watch_writes_events_to_file_sink(tmp_path, capsys) -> None:
    path = tmp_path / "audit.ndjson"
    sink = FileSink(path)
    result = run_watch(
        [_ok_operation("disk"), _ok_operation("memory")],
        sink,
        interval_seconds=60,
        runs=2,
        sleep=lambda seconds: None,
    )
    assert result == 0
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4  # 2 operations x 2 runs
    events = [json.loads(line) for line in lines]
    assert {event["data"]["operation"] for event in events} == {"disk", "memory"}
    err = capsys.readouterr().err
    assert "iteration 1" in err
    assert "iteration 2" in err
    assert capsys.readouterr().out == ""


def test_run_watch_rejects_bad_configuration(tmp_path, capsys) -> None:
    sink = FileSink(tmp_path / "audit.ndjson")
    assert run_watch([], sink, runs=1) == 2
    assert run_watch([_ok_operation()], sink, interval_seconds=0, runs=1) == 2
    assert run_watch([_ok_operation()], sink, interval_seconds=10, runs=-1) == 2
    sink.close()


def test_run_watch_sink_failure_returns_two(tmp_path, capsys) -> None:
    class BrokenSink(watch.Sink):
        def write_event(self, event):
            raise SinkError("disk full")

    assert run_watch([_ok_operation()], BrokenSink(), runs=1, sleep=lambda s: None) == 2
    assert "disk full" in capsys.readouterr().err


def test_run_watch_handles_keyboard_interrupt(tmp_path, capsys) -> None:
    def interrupt(seconds):
        raise KeyboardInterrupt

    sink = FileSink(tmp_path / "audit.ndjson")
    result = run_watch([_ok_operation()], sink, interval_seconds=60, runs=0, sleep=interrupt)
    assert result == 0
    assert "interrupted" in capsys.readouterr().err


def test_run_watch_closes_sink(tmp_path) -> None:
    closed = []

    class ClosingSink(FileSink):
        def close(self):
            closed.append(True)
            super().close()

    sink = ClosingSink(tmp_path / "audit.ndjson")
    run_watch([_ok_operation()], sink, runs=1, sleep=lambda s: None)
    assert closed == [True]
