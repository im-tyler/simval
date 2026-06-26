import numpy as np

from simval.diagnostics.equilibration import (
    check_equilibration,
    effective_sample_size,
    integrated_autocorr_time,
)
from simval.fixtures import drifting_energy_series, good_energy_series


def test_good_series_equilibrates():
    result = check_equilibration(good_energy_series())
    assert result.passed is True
    assert result.detail["effective_sample_size"] > 100


def test_drifting_series_does_not_equilibrate():
    result = check_equilibration(drifting_energy_series())
    assert result.passed is False


def test_ess_decreases_with_correlation():
    rng = np.random.default_rng(0)
    white = rng.normal(0.0, 1.0, 4000)
    correlated = np.cumsum(rng.normal(0.0, 1.0, 4000))
    assert effective_sample_size(white) > effective_sample_size(correlated)


def test_white_noise_low_autocorr():
    rng = np.random.default_rng(1)
    tau = integrated_autocorr_time(rng.normal(0.0, 1.0, 4000))
    assert tau < 3.0
