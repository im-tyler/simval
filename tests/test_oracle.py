import shutil

import pytest

from simval.oracle import compare_metrics, list_cases, validate

pytest.importorskip("MDAnalysis")
datafiles = pytest.importorskip("MDAnalysisTests.datafiles")


def test_cases_available():
    cases = list_cases()
    assert "adk_morph" in cases


def test_compare_metrics_match():
    cand = {"n_selected_atoms": 214, "mean_rmsd_nm": 1.50, "mean_rg_nm": 2.24}
    ref = {"n_selected_atoms": 214, "mean_rmsd_nm": 1.514, "mean_rg_nm": 2.236}
    result = compare_metrics(cand, ref)
    assert result["__passed__"] is True


def test_compare_metrics_drift():
    cand = {"n_selected_atoms": 214, "mean_rmsd_nm": 3.0, "mean_rg_nm": 2.24}
    ref = {"n_selected_atoms": 214, "mean_rmsd_nm": 1.514, "mean_rg_nm": 2.236}
    result = compare_metrics(cand, ref)
    assert result["__passed__"] is False
    assert result["mean_rmsd_nm"]["passed"] is False
    assert result["mean_rg_nm"]["passed"] is True


def test_compare_exact_atom_count():
    cand = {"n_selected_atoms": 215}
    ref = {"n_selected_atoms": 214}
    assert compare_metrics(cand, ref)["__passed__"] is False


def test_validate_unknown_case_raises():
    with pytest.raises(KeyError):
        validate(".", "nonexistent_case_xyz")


def test_validate_cross_domain_mismatch_fails(tmp_path):
    run = tmp_path / "adk"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    result = validate(run, "kepler_two_body")  # MD run vs N-body case
    assert result.passed is False
    assert result.detail["n_checked"] == 0


def test_validate_adk_self_match(tmp_path):
    run = tmp_path / "adk"
    run.mkdir()
    shutil.copy(datafiles.XTC, run / "traj.xtc")
    shutil.copy(datafiles.GRO, run / "conf.gro")
    result = validate(run, "adk_morph")
    assert result.passed is True, result.detail
    assert result.detail["n_failed"] == 0
