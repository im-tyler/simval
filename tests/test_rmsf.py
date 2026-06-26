import numpy as np
import pytest

from simval.diagnostics.rmsf import check_rmsf, per_residue_rmsf


def test_rmsf_zero_for_rigid_frames():
    rng = np.random.default_rng(0)
    base = rng.uniform(0, 5, (20, 3))
    positions = np.stack([base] * 50)
    result = check_rmsf(positions, base, threshold_nm=0.001)
    assert result.passed is True
    assert result.detail["max_rmsf_nm"] < 1e-6


def test_rmsf_flags_high_mobility_residue():
    rng = np.random.default_rng(1)
    base = rng.uniform(0, 5, (20, 3))
    frames = np.stack([base] * 50)
    frames[:, 5, :] += np.linspace(0, 1.0, 50)[:, None]
    result = check_rmsf(frames, base, threshold_nm=0.1)
    assert result.passed is False
    assert result.detail["top10"][0]["index"] == 5


def test_rmsf_translation_invariant():
    rng = np.random.default_rng(2)
    base = rng.uniform(0, 5, (15, 3))
    frames = np.stack([base + np.array([k, 0.0, 0.0]) for k in range(20)])
    r = per_residue_rmsf(frames, base)
    assert np.all(r < 1e-6)


datafiles = pytest.importorskip("MDAnalysisTests.datafiles", reason="needs MDAnalysisTests")


def test_rmsf_on_real_adk():
    from simval.io import load_trajectory

    positions, reference, _ = load_trajectory(
        datafiles.XTC, datafiles.GRO, selection="protein and name CA")
    result = check_rmsf(positions, reference)
    assert result.name == "per_residue_rmsf"
    assert result.detail["n_residues"] == positions.shape[1]
    assert result.value >= 0.0
