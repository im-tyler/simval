import numpy as np

from simval.diagnostics.rmsd import check_rmsd_plateau, rmsd
from simval.fixtures import good_positions, unfolding_positions


def test_rmsd_self_is_zero():
    p = good_positions()
    assert rmsd(p[0], p[0]) < 1e-9


def test_rmsd_translation_invariant():
    p = good_positions()
    shifted = p[5] + np.array([10.0, 0.0, 0.0])
    assert rmsd(shifted, p[5]) < 1e-6


def test_good_positions_plateau_passes():
    pos = good_positions()
    result = check_rmsd_plateau(pos, pos[0])
    assert result.passed is True
    assert result.detail["mean_tail_rmsd_nm"] < 0.1


def test_unfolding_positions_fail():
    pos = unfolding_positions()
    result = check_rmsd_plateau(pos, pos[0])
    assert result.passed is False


def test_max_rmsd_level_gate():
    pos = good_positions()
    strict = check_rmsd_plateau(pos, pos[0], max_rmsd=1e-6)
    assert strict.passed is False
    assert strict.detail["passes_level"] is False
