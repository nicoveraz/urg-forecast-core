"""The urg-forecast command: help, demo output and error paths."""

from __future__ import annotations

import zipfile
from datetime import date

import pytest

from urgencias_core import cli
from urgencias_core.data.deis import facilities_in_file, facility_code_variants
from urgencias_core.pipeline import load_deis, run_forecast, weekly_series
from urgencias_core.report import summary_text


def test_help_lists_subcommands(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    for word in (
        "demo",
        "buscar",
        "pronosticar",
        "modelos",
        "flujo típico",
        "aproximación inicial",
    ):
        assert word in out


@pytest.mark.parametrize("command", ["demo", "buscar", "pronosticar", "modelos"])
def test_each_subcommand_help_has_examples(command, capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main([command, "--help"])
    out = capsys.readouterr().out
    assert "ejemplos:" in out
    assert f"urg-forecast {command}" in out


def test_version_flag(capsys) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.startswith("urg-forecast ")


def _capture_load_deis(monkeypatch) -> dict:
    from urgencias_core import pipeline

    seen: dict = {}

    def fake_load_deis(codes, **kwargs):
        seen.update(kwargs)
        raise pipeline.NoDataError("stop")

    monkeypatch.setattr(pipeline, "load_deis", fake_load_deis)
    return seen


def test_cache_option_reaches_load_deis(tmp_path, monkeypatch) -> None:
    seen = _capture_load_deis(monkeypatch)
    assert cli.main(["pronosticar", "24-105", "--cache", str(tmp_path / "c")]) == 1
    assert seen["cache_dir"] == tmp_path / "c"


def test_cache_defaults_to_env_var(tmp_path, monkeypatch) -> None:
    seen = _capture_load_deis(monkeypatch)
    monkeypatch.setenv(cli.CACHE_ENV, str(tmp_path / "env"))
    assert cli.main(["pronosticar", "24-105"]) == 1
    assert seen["cache_dir"] == tmp_path / "env"


def test_no_command_prints_help(capsys) -> None:
    assert cli.main([]) == 0
    assert "pronosticar" in capsys.readouterr().out


def test_invalid_horizon_is_rejected(capsys) -> None:
    with pytest.raises(SystemExit):
        cli.main(["pronosticar", "24-105", "--horizonte", "seis"])
    assert "horizonte inválido" in capsys.readouterr().err


def test_demo_prints_ascii_tables_and_writes_files(tmp_path, capsys) -> None:
    assert cli.main(["demo", "--offline", "-H", "4", "-o", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Hospital de Puerto Montt (24-105)" in out
    assert "Hospital de Frutillar (24-115)" in out
    assert "+---" in out and "| Modelo" in out
    assert "Horizonte  4 semanas" in out
    for folder in ("24-105_hospital-de-puerto-montt", "24-115_hospital-de-frutillar"):
        d = tmp_path / folder
        for name in ("resumen.txt", "pronostico.csv", "backtest.csv", "pronostico.png"):
            assert (d / name).exists(), name
        header = (d / "pronostico.csv").read_text().splitlines()[0]
        assert header == "timestamp,q50,q80,q90,q95"
        assert len((d / "pronostico.csv").read_text().splitlines()) == 5


def test_pronosticar_offline_unknown_code_fails_cleanly(tmp_path, capsys) -> None:
    assert cli.main(["pronosticar", "09-999", "--offline", "-o", str(tmp_path)]) == 1
    assert "snapshot offline" in capsys.readouterr().err


def test_summary_flags_stale_data() -> None:
    df = load_deis(["24-115"], offline=True)
    result = run_forecast(weekly_series(df, "24-115"), 4, code="24-115", name="F")
    assert "Atención" in summary_text(result, today=date(2030, 1, 1))
    last = result.history["timestamp"].iloc[-1].date()
    assert "Atención" not in summary_text(result, today=last)


def test_facility_code_variants_both_formats() -> None:
    assert facility_code_variants("24-105") >= {"24-105", "124105"}
    assert facility_code_variants("124115") >= {"124115", "24-115"}
    assert facility_code_variants("ABC") == {"ABC"}


def test_facilities_in_file_lists_unique_pairs(tmp_path) -> None:
    csv = (
        "IdEstablecimiento;NEstablecimiento;fecha;GlosaCausa;Total\n"
        "24-105;Hospital de Puerto Montt;01/01/2024;X;10\n"
        "24-105;Hospital de Puerto Montt;02/01/2024;X;12\n"
        "24-115;Hospital de Frutillar;01/01/2024;X;3\n"
    )
    path = tmp_path / "AtencionesUrgencia2024.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("AtencionesUrgencia2024.csv", csv.encode("latin-1"))
    assert sorted(facilities_in_file(path, 2024)["facility_code"]) == ["24-105", "24-115"]


def test_single_model_option(tmp_path, capsys) -> None:
    code = cli.main(["demo", "--offline", "-H", "4", "-m", "MSTL", "-o", str(tmp_path)])
    assert code == 0
    out = capsys.readouterr().out
    assert "MSTL *" in out and "AutoARIMA" not in out


def test_unknown_model_fails_cleanly(tmp_path, capsys) -> None:
    assert cli.main(["demo", "--offline", "-m", "nada", "-o", str(tmp_path)]) == 2
    assert "modelo desconocido" in capsys.readouterr().err


def test_modelos_lists_defaults_and_extras(capsys) -> None:
    assert cli.main(["modelos"]) == 0
    out = capsys.readouterr().out
    for name in ("AutoARIMA", "MSTL", "TBATS", "Ensamble", "ArmónicoFeriados"):
        assert name in out


def test_fuente_option_reaches_load_deis(monkeypatch) -> None:
    seen = _capture_load_deis(monkeypatch)
    assert cli.main(["pronosticar", "24-105"]) == 1
    assert seen["source"] == "repo"
    assert cli.main(["pronosticar", "24-105", "--fuente", "deis"]) == 1
    assert seen["source"] == "deis"
