"""Guards for packaging correctness: the default demo fixture must resolve and
load from the *installed package location*, not from a repo-relative path.

This is a regression test for the bug where the server's default fixture was
resolved via ``Path(__file__).parents[3] / "tests" / "fixtures"``, which only
exists in a source checkout and breaks in an installed wheel.
"""

from __future__ import annotations

from pathlib import Path

import urgencias_core
from urgencias_core._optional import missing_extra_error
from urgencias_core.data.loader import load_visits
from urgencias_core.server.config import DataConfig, default_fixture_path


def test_missing_extra_error_names_extra_and_install_command() -> None:
    err = missing_extra_error("models", "LGBQuantileForecaster")
    assert isinstance(err, ImportError)
    msg = str(err)
    assert "LGBQuantileForecaster" in msg
    assert "urgencias-core[models]" in msg
    assert "pip install" in msg


def test_default_fixture_exists_and_is_inside_the_package() -> None:
    path = default_fixture_path()
    assert path.exists(), f"packaged demo fixture missing at {path}"
    # Must live under the importable package, so it ships in the wheel and works
    # regardless of the current working directory or a source checkout.
    package_dir = Path(urgencias_core.__file__).resolve().parent
    assert package_dir in path.resolve().parents


def test_data_config_default_points_at_packaged_fixture() -> None:
    cfg = DataConfig()
    assert cfg.parquet == default_fixture_path()
    assert cfg.parquet.exists()


def test_packaged_fixture_loads_as_visit_level_frame() -> None:
    visits = load_visits(default_fixture_path())
    assert not visits.empty
    for col in ("arrival", "discharge", "acuity"):
        assert col in visits.columns
