import json
import shutil
from pathlib import Path

import pytest

from simval.wave import WaveEngine, check_cfl, check_wave_energy, integrate_wave
from simval.oracle import get_case, list_cases, validate
from simval.oracle.validate import compare_metrics, compute_metrics
from simval.pipeline import diagnose

EXAMPLE = Path(__file__).parent.parent / "examples" / "wave" / "pulse"


def test_cfl_passes_for_stable_scheme():
    assert check_cfl(0.5).passed is True


def test_cfl_fails_when_unstable():
    r = check_cfl(1.5)
    assert r.passed is False
    assert r.value == 1.5


def test_wave_engine_detects_wave_json():
    assert WaveEngine().detect(EXAMPLE) is True


def test_stable_pulse_energy_bounded():
    cfg = json.loads((EXAMPLE / "wave.json").read_text())
    data = integrate_wave(cfg)
    assert check_cfl(data["cfl"]).passed
    assert check_wave_energy(data["energy"], src_on_index=data["src_on"] // 4).passed


def test_unstable_scheme_energy_explodes():
    cfg = json.loads((EXAMPLE / "wave.json").read_text())
    cfg["dt"] = 0.2  # cfl = 1*0.2/0.1 = 2.0 -> unstable
    data = integrate_wave(cfg)
    assert check_cfl(data["cfl"]).passed is False
    assert check_wave_energy(data["energy"], src_on_index=data["src_on"] // 4).passed is False


def test_diagnose_wave_run(tmp_path):
    run = tmp_path / "w"
    run.mkdir()
    shutil.copy(EXAMPLE / "wave.json", run / "wave.json")
    manifest = diagnose(run, selection="n/a")
    names = [d["name"] for d in manifest["diagnostics"]]
    assert "cfl_stability" in names
    assert "wave_energy_bounded" in names
    assert manifest["verdict"] == "pass"


def test_oracle_wave_flags_unstable_end_to_end(tmp_path):
    run = tmp_path / "bad"
    run.mkdir()
    cfg = json.loads((EXAMPLE / "wave.json").read_text())
    cfg["dt"] = 0.2  # cfl = 2.0 -> unstable scheme
    (run / "wave.json").write_text(json.dumps(cfg))
    result = validate(run, "wave_pulse_stable")
    assert result.passed is False, "unstable scheme must be flagged as DRIFT by the oracle"
