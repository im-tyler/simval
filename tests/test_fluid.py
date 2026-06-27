import json
import shutil
from pathlib import Path

import pytest

from simval.fluid import FluidEngine, check_mass_conservation, check_tau_stability, integrate_fluid
from simval.oracle import validate
from simval.pipeline import diagnose

EXAMPLE = Path(__file__).parent.parent / "examples" / "fluid" / "flow"


def _load():
    return json.loads((EXAMPLE / "fluid.json").read_text())


def test_tau_stability_bounds():
    assert check_tau_stability(0.8).passed is True
    assert check_tau_stability(0.4).passed is False
    assert check_tau_stability(3.0).passed is False


def test_fluid_engine_detects_fluid_json():
    assert FluidEngine().detect(EXAMPLE) is True


def test_lbm_conerves_mass():
    data = integrate_fluid(_load())
    assert check_tau_stability(data["tau"]).passed
    mass = check_mass_conservation(data["mass"])
    assert mass.passed, f"mass drifted: {mass.value}"
    assert mass.value < 1e-6


def test_diagnose_fluid_run(tmp_path):
    run = tmp_path / "fl"
    run.mkdir()
    shutil.copy(EXAMPLE / "fluid.json", run / "fluid.json")
    manifest = diagnose(run, selection="n/a")
    names = [d["name"] for d in manifest["diagnostics"]]
    assert "lbm_tau_stability" in names
    assert "mass_conservation" in names
    assert manifest["verdict"] == "pass"


def test_oracle_flags_unstable_tau(tmp_path):
    run = tmp_path / "bad"
    run.mkdir()
    cfg = _load()
    cfg["tau"] = 0.3  # unstable
    (run / "fluid.json").write_text(json.dumps(cfg))
    result = validate(run, "fluid_flow_stable")
    assert result.passed is False
