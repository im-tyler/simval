from __future__ import annotations

from collections.abc import Iterable

from simval.result import DiagnosticResult


def check_ff_coverage(
    system_atom_types: Iterable[str],
    ff_atom_types: Iterable[str],
    *,
    system_residues: Iterable[str] | None = None,
    ff_residues: Iterable[str] | None = None,
) -> DiagnosticResult:
    sys_atoms = set(system_atom_types)
    ff_atoms = set(ff_atom_types)
    missing_atoms = sorted(sys_atoms - ff_atoms)
    missing_res: list[str] = []
    if system_residues is not None and ff_residues is not None:
        missing_res = sorted(set(system_residues) - set(ff_residues))
    n_missing = len(missing_atoms) + len(missing_res)
    return DiagnosticResult(
        name="ff_coverage",
        passed=n_missing == 0,
        threshold=0.0,
        value=float(n_missing),
        detail={
            "missing_atom_types": missing_atoms,
            "missing_residues": missing_res,
            "n_missing": int(n_missing),
            "n_system_atom_types": len(sys_atoms),
            "n_ff_atom_types": len(ff_atoms),
        },
    )
