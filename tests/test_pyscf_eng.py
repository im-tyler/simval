from pathlib import Path

import pytest

pytest.importorskip("pyscf", reason="needs pyscf")

import simval.pyscf_eng  # noqa: F401  (registers PyscfEngine at import)
from simval.context import select_engine
from simval.pyscf_eng import (
    PyscfEngine,
    check_energy_sane,
    check_scf_convergence,
    run_scf,
)
from simval.oracle import get_case, list_cases

EXAMPLE = Path(__file__).parent.parent / "examples" / "qc" / "h2"


def test_pyscf_engine_detects_molecule_json():
    assert PyscfEngine().detect(EXAMPLE) is True


def test_select_engine_finds_pyscf_for_qc_run():
    assert select_engine(EXAMPLE).name == "qc-pyscf"


def test_h2_scf_converges():
    data = run_scf(EXAMPLE / "molecule.json")
    conv = check_scf_convergence(data["scf_energies"])
    assert conv.passed, conv.detail
    assert conv.name == "scf_convergence"


def test_h2_energy_is_sane_and_around_minus_1_1_hartree():
    data = run_scf(EXAMPLE / "molecule.json")
    sane = check_energy_sane(data["final_energy"], data["n_electrons"])
    assert sane.passed, sane.detail
    assert sane.name == "energy_sane"
    assert data["n_electrons"] == 2
    assert data["final_energy"] == pytest.approx(-1.117, abs=1e-2)


def test_load_context_populates_extra_and_run_params():
    ctx = PyscfEngine().load_context(EXAMPLE, selection="n/a")
    assert ctx.extra["final_energy"] < 0.0
    assert ctx.extra["n_electrons"] == 2
    assert isinstance(ctx.extra["scf_energies"], list)
    assert len(ctx.extra["scf_energies"]) >= 1
    assert ctx.run_params["engine"] == "qc-pyscf"
    assert ctx.run_params["domain"] == "quantum-chemistry"
    assert ctx.run_params["basis"] == "sto3g"


def test_energy_sane_flags_broken_positive_energy():
    broken = check_energy_sane(1.5, n_electrons=2)
    assert broken.passed is False


def test_scf_convergence_handles_single_cycle():
    res = check_scf_convergence([-1.0])
    assert res.passed is True


def test_h2_reference_case_exists_and_matches_fresh_run():
    assert "h2_rhf" in list_cases()
    case = get_case("h2_rhf")
    assert case.engine == "qc-pyscf"
    data = run_scf(EXAMPLE / "molecule.json")
    assert data["final_energy"] == pytest.approx(
        case.reference_metrics["final_energy"], abs=1e-10
    )
    assert data["n_electrons"] == case.reference_metrics["n_electrons"]
