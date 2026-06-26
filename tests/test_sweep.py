import shutil
from pathlib import Path

import pytest

datafiles = pytest.importorskip("MDAnalysisTests.datafiles", reason="needs datafiles")

from simval.sweep import sweep

NBODY = Path(__file__).parent.parent / "examples" / "nbody" / "two_body"
WAVE = Path(__file__).parent.parent / "examples" / "wave" / "pulse"


def _adk(tmp_path, name):
    run = tmp_path / name
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    return run


def test_sweep_across_domains(tmp_path):
    root = tmp_path / "sweeps"
    root.mkdir()
    _adk(root, "run_a")
    _adk(root, "run_b")
    (root / "nbody").mkdir()
    shutil.copy(NBODY / "system.json", root / "nbody" / "system.json")
    (root / "wave").mkdir()
    shutil.copy(WAVE / "wave.json", root / "wave" / "wave.json")

    out = sweep(root)
    assert out["n"] == 4
    names = {r["run"] for r in out["runs"]}
    assert names == {"run_a", "run_b", "nbody", "wave"}
    assert not any("_error" in r for r in out["runs"])


def test_sweep_baseline_deltas(tmp_path):
    root = tmp_path / "b"
    root.mkdir()
    a = _adk(root, "a")
    _adk(root, "b")
    out = sweep(root, baseline=str(a))
    assert out["baseline"] is not None
