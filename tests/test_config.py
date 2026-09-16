import json

import pytest

from autoops.config import Config, load_config


def test_load_config_defaults() -> None:
    assert load_config(None) == Config()


def test_load_config_from_json(tmp_path) -> None:
    path = tmp_path / "autoops.json"
    path.write_text(json.dumps({"json_output": True, "disk_warning_percent": 75, "disk_min_free_gib": 10}), encoding="utf-8")

    config = load_config(path)

    assert config.json_output is True
    assert config.disk_warning_percent == 75.0
    assert config.disk_min_free_gib == 10.0


@pytest.mark.parametrize(
    "payload",
    [
        {"unknown": True},
        {"json_output": "yes"},
        {"disk_warning_percent": -1},
        {"disk_warning_percent": 101},
        {"disk_min_free_gib": -1},
        {"disk_min_free_gib": "ten"},
    ],
)
def test_invalid_config_is_rejected(tmp_path, payload) -> None:
    path = tmp_path / "autoops.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_config(path)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("disk_warning_percent", float("nan")),
        ("disk_warning_percent", float("inf")),
        ("disk_warning_percent", float("-inf")),
        ("disk_min_free_gib", float("nan")),
        ("disk_min_free_gib", float("inf")),
        ("disk_min_free_gib", float("-inf")),
    ],
)
def test_non_finite_numeric_config_is_rejected(key, value) -> None:
    with pytest.raises(ValueError, match="must be finite"):
        Config.from_mapping({key: value})


def test_invalid_json_is_rejected(tmp_path) -> None:
    path = tmp_path / "autoops.json"
    path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        load_config(path)
