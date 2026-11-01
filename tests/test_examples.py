"""The scripts in examples/ run end to end (offline DEIS snapshot, few windows)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), EXAMPLES / name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_example_is_covered() -> None:
    scripts = sorted(p.name for p in EXAMPLES.glob("[0-9]*.py"))
    assert scripts == sorted(CASES), "add new examples to CASES"


# Fast arguments for each example; OUT is replaced by a temporary folder.
CASES = {
    "01_pronostico.py": ["--offline", "-H", "8", "--salida", "OUT"],
    "02_backtest.py": [
        "--offline",
        "--ventanas",
        "2",
        "-m",
        "SeasonalNaive",
        "-m",
        "Armónico",
        "--salida",
        "OUT",
    ],
    "03_modelo_propio.py": ["--offline", "--ventanas", "2"],
    "04_regresor_externo.py": ["--offline", "--ventanas", "2", "--salida", "OUT"],
    "05_analisis.py": ["--offline", "--salida", "OUT"],
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_example_runs(name: str, tmp_path: Path, capsys) -> None:
    module = _load(name)
    args = [str(tmp_path) if a == "OUT" else a for a in CASES[name]]
    if name.startswith("04"):
        from urgencias_core.data.mirror import MirrorUnavailable

        try:
            from urgencias_core.data.flunet import load_flunet

            load_flunet()
        except MirrorUnavailable:
            pytest.skip("FluNet copy not reachable (needs network)")
    module.main(args)
    out = capsys.readouterr().out
    assert out.strip()
    if "OUT" in CASES[name]:
        assert any(tmp_path.rglob("*.png"))
