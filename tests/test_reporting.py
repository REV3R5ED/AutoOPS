import csv
import io
import json

import pytest

from autoops.cli import build_parser, main
from autoops.reporting import to_csv


def test_to_csv_uses_explicit_stable_schema() -> None:
    text = to_csv({"state": "ok", "value": 42}, fields=("value", "state"))
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows == [{"value": "42", "state": "ok"}]


def test_to_csv_rejects_nested_values() -> None:
    with pytest.raises(ValueError, match="scalar"):
        to_csv({"data": {"secret": "not-written"}}, fields=("data",))


def test_disk_cli_csv(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path), "--csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert result == 0
    assert len(rows) == 1
    assert rows[0]["path"] == str(tmp_path.resolve())
    assert rows[0]["state"] in {"ok", "warning"}
    assert rows[0]["warning_percent"] == "90.0"


def test_environment_cli_csv(capsys) -> None:
    result = main(["environment", "--csv"])
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert result == 0
    assert len(rows) == 1
    assert rows[0]["hostname"]
    assert rows[0]["python_version"]


def test_json_and_csv_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["environment", "--json", "--csv"])
    assert exc.value.code == 2
