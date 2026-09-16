import csv
import io
import json

import pytest

from autoops.cli import build_parser, main
from autoops.reporting import to_csv


def _read_csv(text: str) -> list[dict[str, str]]:
    """Read generated CSV with the newline contract required by csv readers."""
    return list(csv.DictReader(io.StringIO(text, newline="")))


def test_to_csv_uses_explicit_stable_schema() -> None:
    text = to_csv({"state": "ok", "value": 42}, fields=("value", "state"))
    rows = _read_csv(text)
    assert rows == [{"value": "42", "state": "ok"}]


def test_to_csv_rejects_nested_values() -> None:
    with pytest.raises(ValueError, match="scalar"):
        to_csv({"data": {"secret": "not-written"}}, fields=("data",))


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-2+3", "@SUM(A1:A2)"])
def test_to_csv_neutralizes_spreadsheet_formula_prefixes(value: str) -> None:
    text = to_csv({"value": value}, fields=("value",))
    rows = _read_csv(text)
    assert rows == [{"value": "'" + value}]


@pytest.mark.parametrize("value", [" =1+1", "\t+cmd", "\r-2+3", "\n@SUM(A1:A2)"])
def test_to_csv_neutralizes_formula_prefixes_after_leading_whitespace(value: str) -> None:
    text = to_csv({"value": value}, fields=("value",))
    rows = _read_csv(text)
    assert rows == [{"value": "'" + value}]


def test_to_csv_does_not_modify_ordinary_strings_or_numbers() -> None:
    text = to_csv({"label": " healthy", "value": 42}, fields=("label", "value"))
    rows = _read_csv(text)
    assert rows == [{"label": " healthy", "value": "42"}]


def test_disk_cli_csv(tmp_path, capsys) -> None:
    result = main(["disk", str(tmp_path), "--csv"])
    rows = _read_csv(capsys.readouterr().out)
    assert result == 0
    assert len(rows) == 1
    assert rows[0]["path"] == str(tmp_path.resolve())
    assert rows[0]["state"] in {"ok", "warning"}
    assert rows[0]["warning_percent"] == "90.0"


def test_environment_cli_csv(capsys) -> None:
    result = main(["environment", "--csv"])
    rows = _read_csv(capsys.readouterr().out)
    assert result == 0
    assert len(rows) == 1
    assert rows[0]["hostname"]
    assert rows[0]["python_version"]


def test_json_and_csv_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["environment", "--json", "--csv"])
    assert exc.value.code == 2
