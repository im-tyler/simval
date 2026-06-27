from simval.freesolv import check_against_experiment, list_compounds, lookup, search


def test_freesolv_has_642_compounds():
    assert len(list_compounds()) == 642


def test_freesolv_lookup():
    info = lookup("mobley_1743409")
    assert info["expt_dG_kcal_mol"] == -5.71
    assert "iupac" in info
    assert "smiles" in info


def test_freesolv_check_passes_within_uncertainty():
    r = check_against_experiment(-5.5, "mobley_1743409")  # -5.71 ± 0.6
    assert r.passed is True
    assert abs(r.detail["deviation_kcal_mol"] - 0.21) < 0.01


def test_freesolv_check_fails_outside_uncertainty():
    r = check_against_experiment(20.0, "mobley_1743409")
    assert r.passed is False


def test_freesolv_search_by_name():
    hits = search("benzene")
    assert len(hits) >= 1
    assert any("benzene" in h["iupac"].lower() for h in hits)


def test_freesolv_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        lookup("nonexistent_xyz")
