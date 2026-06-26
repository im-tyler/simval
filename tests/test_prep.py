import pytest

pytest.importorskip("MDAnalysis")
datafiles = pytest.importorskip("MDAnalysisTests.datafiles")

from simval.diagnostics.prep import check_box_cutoff, check_steric_clashes


def test_box_cutoff_passes_real_adk():
    result = check_box_cutoff(datafiles.GRO, rcoulomb=1.0)
    assert result.name == "box_cutoff"
    assert "min_box_edge_nm" in result.detail


def test_box_cutoff_fails_when_rcoulomb_exceeds_half_box():
    result = check_box_cutoff(datafiles.GRO, rcoulomb=1.0e6)
    assert result.passed is False
    assert result.value < 2.0


def test_clashes_run_on_real_structure():
    result = check_steric_clashes(datafiles.GRO, threshold=0.8)
    assert result.name == "steric_clashes"
    assert isinstance(result.detail["n_clashes"], int)
    assert result.detail["n_clashes"] >= 0
