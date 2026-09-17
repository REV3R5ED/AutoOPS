from importlib.metadata import version

import autoops


def test_runtime_version_matches_package_metadata() -> None:
    assert autoops.__version__ == version("autoops-toolkit")


def test_portfolio_release_version() -> None:
    assert autoops.__version__ == "0.3.0"
