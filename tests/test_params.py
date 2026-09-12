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


# --- PAR-001: non-finite quantities are rejected before range checks ---


import pytest


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_dt_fails_params_diagnostic(bad):
    result = check_params({"dt": Quantity(bad, "ps")})
    assert result.passed is False
    assert any("must be finite" in v for v in result.detail["violations"])


def test_nonfinite_ref_t_nan_from_json_fails_diagnose(tmp_path):
    # params.json carries the JSON NaN literal; json.loads accepts it, so
    # the diagnostic itself must reject the value.
    import json

    from simval.fixtures import make_run_dir
    from simval.pipeline import diagnose

    run = make_run_dir(tmp_path / "nan_params", good=True)
    raw = json.loads((run / "params.json").read_text())
    raw["dt"] = {"value": float("nan"), "unit": "ps"}
    (run / "params.json").write_text(json.dumps(raw))
    manifest = diagnose(run, selection="protein")
    params_diag = next(d for d in manifest["diagnostics"] if d["name"] == "params")
    assert params_diag["passed"] is False
    assert "must be finite" in params_diag["detail"]["violations"][0]
    assert manifest["verdict"] == "fail"
