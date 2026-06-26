from simval.diagnostics.params import check_params
from simval.fixtures import BAD_PARAMS, GOOD_PARAMS
from simval.units import Quantity


def _q(d):
    return {k: Quantity(v["value"], v["unit"]) for k, v in d.items()}


def test_good_params_pass():
    assert check_params(_q(GOOD_PARAMS)).passed is True


def test_bad_params_fail_with_violations():
    result = check_params(_q(BAD_PARAMS))
    assert result.passed is False
    assert result.detail["n_violations"] >= 2
    joined = " ".join(result.detail["violations"])
    assert "dt" in joined
    assert "nsteps" in joined


def test_unknown_params_ignored():
    result = check_params({"dt": Quantity(0.002, "ps"), "mystery": Quantity(1, "nm")})
    assert result.passed is True
    assert result.detail["checked"] == 1
