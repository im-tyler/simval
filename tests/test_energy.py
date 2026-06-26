import numpy as np

from simval.diagnostics.energy import check_energy_drift
from simval.fixtures import drifting_energy_series, good_energy_series


def test_good_energy_passes():
    result = check_energy_drift(good_energy_series())
    assert result.passed is True
    assert result.name == "energy_drift"
    assert result.value < result.threshold


def test_drifting_energy_fails():
    result = check_energy_drift(drifting_energy_series())
    assert result.passed is False
    assert result.value > result.threshold


def test_skip_fraction_discards_transient():
    series = good_energy_series(n=1000).copy()
    series[:100] += np.linspace(800.0, 0.0, 100)
    result = check_energy_drift(series, skip_fraction=0.1)
    assert result.passed is True


def test_transient_without_skip_fails():
    series = good_energy_series(n=1000).copy()
    series[:100] += np.linspace(800.0, 0.0, 100)
    result = check_energy_drift(series, skip_fraction=0.0)
    assert result.passed is False


def test_result_serializes():
    result = check_energy_drift(good_energy_series())
    d = result.to_dict()
    assert set(d) == {"name", "passed", "threshold", "value", "detail"}
    assert isinstance(result.detail["slope_per_step"], float)


def test_rejects_short_input():
    import pytest

    with pytest.raises(ValueError):
        check_energy_drift(np.array([1.0]))
