import csv
import io
import json
from datetime import datetime

import pytest

from autoops import __version__
from autoops.cli import build_parser, main


def test_cli_version_matches_package_version(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"autoops {__version__}"
    assert __version__ == "0.2.0"


def test_disk_cli_json(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["path"] == str(tmp_path.resolve())
    assert 0 <= payload["used_percent"] <= 100
    assert payload["state"] in {"ok", "warning"}
    assert payload["warning_percent"] == 90.0


def test_disk_cli_missing_path(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path / "missing")])

    assert result == 2
    assert "Path does not exist" in capsys.readouterr().out


def test_cli_config_can_enable_json_and_threshold(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"json_output": true, "disk_warning_percent": 0}', encoding="utf-8")

    result = main(["--config", str(config), "disk", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["state"] == "warning"
    assert payload["warning_percent"] == 0.0


def test_disk_fail_on_warning_returns_one_and_keeps_json_report(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"disk_warning_percent": 0}', encoding="utf-8")

    result = main(["--config", str(config), "disk", str(tmp_path), "--json", "--fail-on-warning"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["state"] == "warning"
    assert payload["warning_percent"] == 0.0


def test_disk_fail_on_warning_does_not_fail_healthy_check(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"disk_warning_percent": 100}', encoding="utf-8")

    result = main(["--config", str(config), "disk", str(tmp_path), "--fail-on-warning"])

    assert result == 0
    assert "State: ok" in capsys.readouterr().out


def test_cli_rejects_bad_config(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"unknown": true}', encoding="utf-8")

    assert main(["--config", str(config), "disk", str(tmp_path)]) == 2
    assert "Unknown configuration key" in capsys.readouterr().out


def test_environment_cli_json(capsys) -> None:
    result = main(["environment", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["hostname"]
    assert payload["platform"]
    assert payload["python_version"]
    assert payload["cpu_count"] is None or payload["cpu_count"] >= 1


def test_preflight_cli_json_combines_environment_and_disk(tmp_path, capsys) -> None:
    result = main(["preflight", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert datetime.fromisoformat(payload["generated_at"].replace("Z", "+00:00")).tzinfo is not None
    assert payload["hostname"]
    assert payload["python_version"]
    assert payload["disk_path"] == str(tmp_path.resolve())
    assert 0 <= payload["disk_used_percent"] <= 100
    assert payload["disk_state"] in {"ok", "warning"}


def test_preflight_cli_csv_has_stable_flat_schema(tmp_path, capsys) -> None:
    result = main(["preflight", str(tmp_path), "--csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))

    assert result == 0
    assert len(rows) == 1
    assert datetime.fromisoformat(rows[0]["generated_at"].replace("Z", "+00:00")).tzinfo is not None
    assert rows[0]["disk_path"] == str(tmp_path.resolve())
    assert rows[0]["hostname"]
    assert rows[0]["disk_state"] in {"ok", "warning"}


def test_preflight_fail_on_warning_preserves_report(tmp_path, capsys) -> None:
    config = tmp_path / "autoops.json"
    config.write_text('{"disk_warning_percent": 0}', encoding="utf-8")

    result = main(["--config", str(config), "preflight", str(tmp_path), "--json", "--fail-on-warning"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 1
    assert payload["disk_state"] == "warning"


def test_preflight_missing_path_is_operational_error(tmp_path, capsys) -> None:
    result = main(["preflight", str(tmp_path / "missing"), "--json"])

    assert result == 2
    assert "Path does not exist" in capsys.readouterr().out
