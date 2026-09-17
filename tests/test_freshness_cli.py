import json
import os
import time

from autoops.cli import main


def test_freshness_cli_json_reports_file_state(tmp_path, capsys) -> None:
    target = tmp_path / "backup.json"
    target.write_text("{}", encoding="utf-8")

    result = main(["freshness", str(target), "--max-age-seconds", "60", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["path"] == str(target.resolve())
    assert payload["size_bytes"] == 2
    assert payload["state"] == "ok"
    assert payload["max_age_seconds"] == 60.0
    assert payload["modified_at"].endswith("Z")


def test_freshness_cli_can_fail_on_stale_without_losing_report(tmp_path, capsys) -> None:
    target = tmp_path / "backup.json"
    target.write_text("{}", encoding="utf-8")
    old = time.time() - 120
    os.utime(target, (old, old))

    result = main(["freshness", str(target), "--max-age-seconds", "60", "--json", "--fail-on-stale"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["state"] == "stale"
    assert payload["age_seconds"] >= 60


def test_freshness_cli_rejects_invalid_threshold(tmp_path, capsys) -> None:
    target = tmp_path / "artifact.txt"
    target.write_text("ok", encoding="utf-8")

    result = main(["freshness", str(target), "--max-age-seconds", "-1"])

    assert result == 2
    assert "finite non-negative number" in capsys.readouterr().out
