import csv
import io
import json

from autoops.artifact_cli import main


def test_artifact_cli_json_reports_healthy_file(tmp_path, capsys) -> None:
    target = tmp_path / "backup.json"
    target.write_text('{"ok": true}', encoding="utf-8")

    result = main([
        str(target),
        "--max-age-seconds", "60",
        "--min-size-bytes", "4",
        "--json",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["state"] == "ok"
    assert payload["path"] == str(target.resolve())
    assert payload["min_size_bytes"] == 4


def test_artifact_cli_health_gate_preserves_json_report(tmp_path, capsys) -> None:
    target = tmp_path / "empty.log"
    target.write_text("", encoding="utf-8")

    result = main([
        str(target),
        "--max-age-seconds", "60",
        "--min-size-bytes", "1",
        "--json",
        "--fail-on-unhealthy",
    ])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["state"] == "undersized"
    assert payload["size_bytes"] == 0


def test_artifact_cli_csv_has_stable_flat_schema(tmp_path, capsys) -> None:
    target = tmp_path / "report.txt"
    target.write_text("ready", encoding="utf-8")

    result = main([str(target), "--max-age-seconds", "60", "--csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))

    assert result == 0
    assert len(rows) == 1
    assert rows[0]["state"] == "ok"
    assert rows[0]["min_size_bytes"] == "0"


def test_artifact_cli_missing_file_is_operational_error(tmp_path, capsys) -> None:
    result = main([str(tmp_path / "missing"), "--max-age-seconds", "60"])

    assert result == 2
    assert "error:" in capsys.readouterr().out
