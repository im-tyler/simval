from pathlib import Path

import pytest

from simval.fetch import _classify, fetch_structure


def test_classify():
    assert _classify("1AKI") == "pdb"
    assert _classify("4HHB") == "pdb"
    assert _classify("P00698") == "alphafold"
    assert _classify("Q8IVF2A9") == "alphafold"


def _online() -> bool:
    import urllib.request
    try:
        urllib.request.urlopen("https://files.rcsb.org", timeout=5)
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _online(), reason="needs network")
def test_fetch_pdb_structure(tmp_path):
    info = fetch_structure("1AKI", tmp_path)
    assert info["source"] == "pdb"
    assert info["bytes"] > 10000
    txt = Path(info["path"]).read_text()
    assert "ATOM" in txt


@pytest.mark.skipif(not _online(), reason="needs network")
def test_fetch_alphafold_structure(tmp_path):
    info = fetch_structure("P00698", tmp_path)  # lysozyme
    assert info["source"] == "alphafold"
    assert info["bytes"] > 10000
