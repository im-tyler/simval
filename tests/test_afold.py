import pytest

from simval.afold import check_plddt_profile


def _online() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("https://alphafold.ebi.ac.uk", timeout=5)
        return True
    except Exception:
        return False


def test_plddt_profile_high_confidence():
    plddt = [95.0] * 100
    r = check_plddt_profile(plddt)
    assert r.passed is True
    assert r.detail["mean_plddt"] == 95.0
    assert r.detail["fraction_below_70"] == 0.0


def test_plddt_profile_flags_low_confidence():
    plddt = [95.0, 40.0, 30.0, 95.0, 95.0]
    r = check_plddt_profile(plddt)
    assert r.detail["low_confidence_residue_indices"] == [1, 2]
    assert r.detail["fraction_below_70"] == pytest.approx(0.4)


def test_plddt_profile_overall_low_warns():
    plddt = [50.0] * 10
    r = check_plddt_profile(plddt)
    assert r.passed is False


@pytest.mark.skipif(not _online(), reason="needs network")
def test_fetch_plddt_real(tmp_path):
    from simval.afold import fetch_plddt

    plddt, path = fetch_plddt("P00698", tmp_path)
    assert len(plddt) > 50
    assert all(0.0 <= v <= 100.0 for v in plddt)
    assert check_plddt_profile(plddt).passed is True  # lysozyme is well-predicted
