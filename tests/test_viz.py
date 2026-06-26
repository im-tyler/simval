import shutil
from pathlib import Path

datafiles = __import__("pytest").importorskip("MDAnalysisTests.datafiles", reason="needs datafiles")

from simval.viz import series_for

EXAMPLE = Path(__file__).parent.parent / "examples" / "nbody" / "two_body"


def test_md_series(tmp_path):
    run = tmp_path / "adk"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    s = series_for(run)
    assert s["engine"] == "gromacs"
    assert "rmsd_nm" in s["series"]
    assert s["orbit"] is None


def test_nbody_series_has_orbit():
    __import__("pytest").importorskip("rebound", reason="needs rebound")
    s = series_for(EXAMPLE, selection="n/a")
    assert s["engine"] == "nbody-rebound"
    assert "energy" in s["series"]
    assert "angular_momentum" in s["series"]
    assert s["orbit"] is not None
    assert len(s["orbit"]) >= 2
    assert set(s["orbit"][0]) == {"x", "y"}
