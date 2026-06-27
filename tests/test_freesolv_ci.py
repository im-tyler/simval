"""CI regression: validate the FreeSolv oracle against a known experimental value.
Ensures the FreeSolv database + check_against_experiment are intact."""
from simval.freesolv import check_against_experiment, lookup


def test_freesolv_regression():
    info = lookup("mobley_1743409")
    assert info["expt_dG_kcal_mol"] == -5.71
    r = check_against_experiment(-5.71, "mobley_1743409")
    assert r.passed  # exact match -> within uncertainty
    assert r.detail["deviation_kcal_mol"] == 0.0
