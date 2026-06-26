import shutil

import pytest

datafiles = pytest.importorskip("MDAnalysisTests.datafiles", reason="needs MDAnalysisTests")

from simval.compare import compare_runs, largest_deltas


def _adk(tmp_path, name):
    run = tmp_path / name
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    return run


def test_self_compare_zero_deltas(tmp_path):
    a = _adk(tmp_path, "a")
    b = _adk(tmp_path, "b")
    comp = compare_runs(a, b)
    assert set(comp["metrics_a"]) == set(comp["metrics_b"])
    for _, d in comp["deltas"].items():
        assert d["delta_rel"] < 1e-9


def test_largest_deltas_sorted(tmp_path):
    a = _adk(tmp_path, "a")
    b = _adk(tmp_path, "b")
    comp = compare_runs(a, b)
    top = largest_deltas(comp, n=3)
    assert len(top) <= 3
    if len(top) > 1:
        assert top[0][1] >= top[1][1]
