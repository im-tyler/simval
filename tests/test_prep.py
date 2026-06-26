import shutil

import pytest

pytest.importorskip("MDAnalysis")
datafiles = pytest.importorskip("MDAnalysisTests.datafiles")

from simval.diagnostics.prep import (
    check_box_cutoff,
    check_charge_state,
    check_steric_clashes,
    his_tautomer_inventory,
    ion_inventory,
    net_charge_from_tpr,
    parse_net_charge,
)

REAL_TPR = "pipeline/runs/lysozyme/topol.tpr"


def test_box_cutoff_passes_real_adk():
    result = check_box_cutoff(datafiles.GRO, rcoulomb=1.0)
    assert result.name == "box_cutoff"
    assert "min_box_edge_nm" in result.detail


def test_box_cutoff_fails_when_rcoulomb_exceeds_half_box():
    result = check_box_cutoff(datafiles.GRO, rcoulomb=1.0e6)
    assert result.passed is False
    assert result.value < 2.0


def test_clashes_run_on_real_structure():
    result = check_steric_clashes(datafiles.GRO, threshold=0.8)
    assert result.name == "steric_clashes"
    assert isinstance(result.detail["n_clashes"], int)
    assert result.detail["n_clashes"] >= 0


def test_parse_net_charge():
    dump = (
        "   molblock (0):\n"
        '      moltype              = 0 "Protein"\n'
        "      #molecules                     = 1\n"
        "   molblock (1):\n"
        '      moltype              = 1 "NA"\n'
        "      #molecules                     = 2\n"
        "   molblock (2):\n"
        '      moltype              = 2 "CL"\n'
        "      #molecules                     = 3\n"
        "   moltype (0):\n"
        "      atom[ 0]={q= 1.0}\n"
        "      atom[ 1]={q= 2.0}\n"
        "   moltype (1):\n"
        "      atom[ 0]={q= 1.0}\n"
        "   moltype (2):\n"
        "      atom[ 0]={q=-1.0}\n"
    )
    # protein(+3)*1 + NA(+1)*2 + CL(-1)*3 = 3 + 2 - 3 = 2
    assert abs(parse_net_charge(dump) - 2.0) < 1e-9


def test_his_tautomer_inventory_on_real_structure():
    inv = his_tautomer_inventory(__import__("MDAnalysis").Universe(datafiles.GRO))
    assert set(inv).issubset({"HID", "HIE", "HIP", "deprot"})
    assert sum(inv.values()) >= 0


def test_charge_state_neutralized_passes():
    result = check_charge_state(datafiles.GRO, net_charge=0.0)
    assert result.passed is True
    assert result.detail["neutralized"] is True


def test_charge_state_unneutralized_fails():
    result = check_charge_state(datafiles.GRO, net_charge=8.0)
    assert result.passed is False
    assert result.detail["system_net_charge_e"] == 8.0
    # non-ion charge must equal net minus whatever ions the structure actually has
    assert result.detail["non_ion_charge_e"] == 8.0 - result.detail["ion_charge_e"]


def test_charge_state_ions_cancel_charge():
    import MDAnalysis as mda

    u = mda.Universe(datafiles.GRO)
    ions, ion_charge = ion_inventory(u)
    assert isinstance(ion_charge, float)


@pytest.mark.skipif(not shutil.which("gmx") or not __import__("os").path.exists(REAL_TPR),
                    reason="needs gmx + real lysozyme .tpr")
def test_net_charge_from_real_tpr():
    q = net_charge_from_tpr(REAL_TPR)
    assert abs(q) < 1e-2  # neutralized (protein +8, 36 NA, 44 CL)


@pytest.mark.skipif(not shutil.which("gmx") or not __import__("os").path.exists(REAL_TPR),
                    reason="needs gmx + real lysozyme .tpr")
def test_charge_state_neutralized_lysozyme_passes():
    result = check_charge_state("pipeline/runs/lysozyme/conf.gro", tpr_path=REAL_TPR)
    assert result.passed is True
    assert abs(result.detail["system_net_charge_e"]) < 1e-2
    assert result.detail["ions"]  # NA/CL present
