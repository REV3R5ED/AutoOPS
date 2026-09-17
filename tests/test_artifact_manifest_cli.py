import csv
import io
import json

from autoops.artifact_cli import main


def _manifest(tmp_path, artifacts):
    path = tmp_path / "artifacts.json"
    path.write_text(json.dumps({"artifacts": artifacts}), encoding="utf-8")
    return path


def test_manifest_json_reports_batch_and_health_gate(tmp_path, capsys) -> None:
    healthy = tmp_path / "backup.json"
    unhealthy = tmp_path / "empty.log"
    healthy.write_text("ready", encoding="utf-8")
    unhealthy.write_text("", encoding="utf-8")
    manifest = _manifest(tmp_path, [
        {"path": str(healthy), "max_age_seconds": 60, "min_size_bytes": 1},
        {"path": str(unhealthy), "max_age_seconds": 60, "min_size_bytes": 1},
    ])

    result = main(["--manifest", str(manifest), "--json", "--fail-on-unhealthy"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["total"] == 2
    assert payload["healthy"] == 1
    assert payload["unhealthy"] == 1
    assert payload["states"]["undersized"] == 1
    assert [item["state"] for item in payload["artifacts"]] == ["ok", "undersized"]


def test_manifest_csv_emits_one_row_per_artifact(tmp_path, capsys) -> None:
    first = tmp_path / "first.txt"
    second = tmp_path / "second.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    manifest = _manifest(tmp_path, [
        {"path": str(first), "max_age_seconds": 60},
        {"path": str(second), "max_age_seconds": 60},
    ])

    result = main(["--manifest", str(manifest), "--csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))

    assert result == 0
    assert len(rows) == 2
    assert [row["state"] for row in rows] == ["ok", "ok"]


def test_manifest_rejects_unknown_keys(tmp_path, capsys) -> None:
    manifest = _manifest(tmp_path, [
        {"path": "report.txt", "max_age_seconds": 60, "command": "do-not-run"},
    ])

    result = main(["--manifest", str(manifest), "--json"])

    assert result == 2
    assert "unknown keys" in capsys.readouterr().out


def test_cli_requires_exactly_one_input_mode(tmp_path, capsys) -> None:
    manifest = _manifest(tmp_path, [])

    assert main([]) == 2
    capsys.readouterr()
    assert main(["some.txt", "--manifest", str(manifest), "--max-age-seconds", "60"]) == 2
