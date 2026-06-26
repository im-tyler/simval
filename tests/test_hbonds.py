import shutil

import pytest

datafiles = pytest.importorskip("MDAnalysisTests.datafiles", reason="needs datafiles")

from simval.diagnostics.hbonds import check_hydrogen_bonds


def test_hbonds_on_real_adk(tmp_path):
    run = tmp_path / "adk"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    result = check_hydrogen_bonds(run / "conf.gro", run / "traj.xtc")
    assert result.name == "hydrogen_bonds"
    assert result.detail["mean_count"] > 0
    assert result.detail["n_frames"] == 10
