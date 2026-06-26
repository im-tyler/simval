import json
import shutil
from pathlib import Path

import pytest

pytest.importorskip("rebound", reason="needs rebound")

from simval.nbody import ReboundEngine, check_angular_momentum, check_com_drift, integrate_system
from simval.oracle import list_cases, validate
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


def test_oracle_kepler_case_exists_and_self_matches():
    assert "kepler_two_body" in list_cases()
    result = validate(EXAMPLE, "kepler_two_body")
    assert result.passed is True


def test_oracle_kepler_flags_bad_candidate():
    from simval.oracle import get_case
    from simval.oracle.validate import compare_metrics

    case = get_case("kepler_two_body")
    bad = dict(case.reference_metrics)
    bad["energy_relative_range"] = 1e-2  # a badly non-conserving integrator
    bad["angular_momentum_relative_range"] = 5e-3
    result = compare_metrics(bad, case.reference_metrics, case.tolerances)
    assert result["__passed__"] is False
    assert result["energy_relative_range"]["passed"] is False
