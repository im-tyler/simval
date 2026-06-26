import shutil
from pathlib import Path

import pytest

pytest.importorskip("rebound", reason="needs rebound")

from simval.nbody import ReboundEngine, check_angular_momentum, check_com_drift, integrate_system
from simval.pipeline import diagnose

EXAMPLE = Path(__file__).parent.parent / "examples" / "nbody" / "two_body"


def test_two_body_conserves_energy_and_angular_momentum():
    data = integrate_system(EXAMPLE / "system.json", samples=100)
    e = data["energy"]
    rel = (e.max() - e.min()) / abs(e.mean())
    assert rel < 1e-6, f"energy not conserved: rel={rel}"
    assert check_angular_momentum(data["L_magnitude"]).passed
    assert check_com_drift(data["com"]).passed


def test_rebound_engine_detects_system_json():
    assert ReboundEngine().detect(EXAMPLE) is True


def test_diagnose_nbody_run_reuses_energy_check_and_adds_domain_checks(tmp_path):
    run = tmp_path / "nb"
    run.mkdir()
    shutil.copy(EXAMPLE / "system.json", run / "system.json")
    manifest = diagnose(run, selection="n/a")
    names = [d["name"] for d in manifest["diagnostics"]]
    assert "energy_drift" in names
    assert "angular_momentum" in names
    assert "com_drift" in names
    assert manifest["verdict"] == "pass"
    assert manifest["params"]["engine"] == "nbody-rebound"
