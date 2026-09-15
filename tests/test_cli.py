import json

from autoops.cli import main


def test_disk_cli_json(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert result == 0
    assert payload["path"] == str(tmp_path.resolve())
    assert 0 <= payload["used_percent"] <= 100


def test_disk_cli_missing_path(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path / "missing")])

    assert result == 2
    assert "Path does not exist" in capsys.readouterr().out
