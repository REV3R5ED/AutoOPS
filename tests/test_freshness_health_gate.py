import json
import os
import time

from autoops.cli import main


def test_fail_on_stale_rejects_future_dated_file(tmp_path, capsys) -> None:
    target = tmp_path / "heartbeat.txt"
    target.write_text("ok", encoding="utf-8")
    future = time.time() + 3600
    os.utime(target, (future, future))

    result = main([
        "freshness",
        str(target),
        "--max-age-seconds",
        "300",
        "--json",
        "--fail-on-stale",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["state"] == "future"


def test_future_dated_file_remains_diagnostic_without_health_gate(tmp_path, capsys) -> None:
    target = tmp_path / "heartbeat.txt"
    target.write_text("ok", encoding="utf-8")
    future = time.time() + 3600
    os.utime(target, (future, future))

    result = main(["freshness", str(target), "--max-age-seconds", "300", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["state"] == "future"
