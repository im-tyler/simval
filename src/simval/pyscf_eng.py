"""Quantum-chemistry domain (PySCF). Proves the EngineAdapter port accepts a
genuinely different physics domain (electronic structure, not MD/N-body/PDE):
runs a real SCF via PySCF and verifies SCF convergence + total-energy sanity.

PySCF is imported lazily so the module registers its engine at import time
without forcing the dependency on every simval install."""
from __future__ import annotations

import json
from pathlib import Path

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def run_scf(molecule_path) -> dict:
    """Build a pyscf.gto.Mole from molecule.json and run SCF, recording the
    per-cycle total-energy sequence via the SCF callback."""
    from pyscf import gto, scf

    cfg = json.loads(Path(molecule_path).read_text())
    atoms = cfg["atoms"]
    basis = cfg.get("basis", "sto3g")
    method = cfg.get("method", "rhf").lower()
    charge = cfg.get("charge", 0)
    spin = cfg.get("spin", 0)
    unit = cfg.get("unit", "Angstrom")

    mol = gto.M(atom=atoms, basis=basis, charge=charge, spin=spin, unit=unit)
    mol.build()

    if method == "uhf":
        mf = scf.UHF(mol)
    elif method == "rohf":
        mf = scf.ROHF(mol)
    else:
        mf = scf.RHF(mol)

    scf_energies: list[float] = []

    def _record(envs) -> None:
        e = envs.get("e_tot") if isinstance(envs, dict) else getattr(envs, "e_tot", None)
        if e is not None:
            scf_energies.append(float(e))

    mf.callback = _record
    mf.kernel()

    final_energy = float(mf.e_tot)
    if not scf_energies:
        scf_energies = [final_energy]

    return {
        "scf_energies": scf_energies,
        "final_energy": final_energy,
        "n_electrons": int(mol.nelectron),
        "converged": bool(mf.converged),
        "method": method,
        "basis": basis,
    }


def check_scf_convergence(energies_per_cycle, *, threshold: float = 1e-6) -> DiagnosticResult:
    """True when the final SCF energy step |E_last - E_prev_last| is below
    `threshold` Hartree. Fewer than two recorded cycles means the initial guess
    was already the solution."""
    e = [float(x) for x in energies_per_cycle]
    n = len(e)
    if n < 2:
        return DiagnosticResult(
            name="scf_convergence",
            passed=True,
            threshold=float(threshold),
            value=0.0,
            detail={"n_cycles": n, "last_delta": 0.0,
                    "note": "fewer than 2 SCF cycles recorded"},
        )
    delta = abs(e[-1] - e[-2])
    return DiagnosticResult(
        name="scf_convergence",
        passed=delta < threshold,
        threshold=float(threshold),
        value=float(delta),
        detail={"last_delta": float(delta), "n_cycles": n,
                "first": float(e[0]), "last": float(e[-1])},
    )


def check_energy_sane(final_energy, n_electrons, *, floor: float = 0.0) -> DiagnosticResult:
    """Sanity check: the HF/DFT total energy of a bound molecule is a large
    negative number. A non-negative total energy signals a broken calculation
    (wrong geometry, unbuilt molecule, wrong charge)."""
    passed = float(final_energy) < floor
    return DiagnosticResult(
        name="energy_sane",
        passed=passed,
        threshold=float(floor),
        value=float(final_energy),
        detail={"n_electrons": int(n_electrons), "floor": float(floor),
                "rule": "HF/DFT total energy of a bound molecule must be negative"},
    )


class PyscfEngine(EngineAdapter):
    name = "qc-pyscf"

    def detect(self, run: Path) -> bool:
        return (run / "molecule.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        data = run_scf(run / "molecule.json")
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {
            "scf_energies": data["scf_energies"],
            "final_energy": data["final_energy"],
            "n_electrons": data["n_electrons"],
            "converged": data["converged"],
            "method": data["method"],
            "basis": data["basis"],
        }
        ctx.run_params = {
            "engine": self.name,
            "domain": "quantum-chemistry",
            "method": data["method"],
            "basis": data["basis"],
            "n_electrons": int(data["n_electrons"]),
            "scf_converged": bool(data["converged"]),
        }
        return ctx


register_engine(PyscfEngine())
