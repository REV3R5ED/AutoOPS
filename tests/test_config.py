import json

import pytest

from autoops.config import Config, load_config


def test_load_config_defaults() -> None:
    assert load_config(None) == Config()


def test_load_config_from_json(tmp_path) -> None:
    path = tmp_path / "autoops.json"
    path.write_text(json.dumps({"json_output": True, "disk_warning_percent": 75}), encoding="utf-8")

    config = load_config(path)

    assert config.json_output is True
    assert config.disk_warning_percent == 75.0


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": True},
        {"json_output": "yes"},
        {"disk_warning_percent": -1},
        {"disk_warning_percent": 101},
    ],
)
def test_invalid_config_is_rejected(tmp_path, payload) -> None:
    path = tmp_path / "autoops.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(path)


def test_invalid_json_is_rejected(tmp_path) -> None:
    path = tmp_path / "autoops.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config(path)
