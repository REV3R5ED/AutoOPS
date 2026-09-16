import json

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
