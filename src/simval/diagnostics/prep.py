from __future__ import annotations

import re

from simval.result import DiagnosticResult

_ION_CHARGES = {
    "NA": 1, "NA+": 1, "K": 1, "CA": 2, "MG": 2, "ZN": 2, "FE": 2,
    "CL": -1, "CL-": -1, "BR": -1, "F": -1,
}

_ATOM_CHARGE = re.compile(r"atom\[\s*\d+\s*\]=\{[^}]*?\bq=\s*([-+0-9.eE]+)")


def parse_net_charge(dump_text: str) -> float:
    qs = _ATOM_CHARGE.findall(dump_text)
    if not qs:
        raise ValueError("no atom charges parsed from gmx dump output")
    return float(sum(float(q) for q in qs))


def net_charge_from_tpr(tpr_path) -> float:
    import subprocess

    out = subprocess.run(
        ["gmx", "dump", "-s", str(tpr_path)],
        capture_output=True, text=True, timeout=180,
    )
    return parse_net_charge(out.stdout)


def ion_inventory(u) -> tuple[dict, float]:
    counts: dict[str, int] = {}
    total = 0.0
    for resname, q in _ION_CHARGES.items():
        n = u.select_atoms(f"resname {resname}").n_residues
        if n:
            counts[resname] = n
            total += q * n
    return counts, float(total)


def his_tautomer_inventory(u) -> dict:
    from collections import Counter

    c: Counter = Counter()
    for r in u.select_atoms("resname HIS").residues:
        names = set(r.atoms.names)
        hd1, he2 = "HD1" in names, "HE2" in names
        label = "HIP" if (hd1 and he2) else "HID" if hd1 else "HIE" if he2 else "deprot"
        c[label] += 1
    return dict(c)


def check_charge_state(
    structure_path,
    *,
    tpr_path=None,
    net_charge: float | None = None,
    tol: float = 0.5,
) -> DiagnosticResult:
    """System net charge + neutralization + His-tautomer transparency.

    Pass when the total system (incl. counterions) is approximately neutral;
    otherwise flag a PME net-charge artifact risk. His tautomers are reported
    for human review (pdb2gmx assigns them silently) — not pass/fail (Tier 2)."""
    import MDAnalysis as mda

    u = mda.Universe(str(structure_path))
    if net_charge is None:
        if tpr_path is None:
            raise ValueError("either net_charge or tpr_path must be provided")
        net_charge = net_charge_from_tpr(tpr_path)

    ions, ion_charge = ion_inventory(u)
    his = his_tautomer_inventory(u)
    protein_charge = float(net_charge) - ion_charge
    passed = abs(float(net_charge)) <= tol

    return DiagnosticResult(
        name="charge_state",
        passed=passed,
        threshold=float(tol),
        value=float(abs(net_charge)),
        detail={
            "system_net_charge_e": float(net_charge),
            "ion_charge_e": float(ion_charge),
            "non_ion_charge_e": float(protein_charge),
            "neutralized": bool(passed),
            "ions": ions,
            "his_tautomers": his,
            "tol_e": float(tol),
            "note": "unneutralized systems cause PME net-charge artifacts; His tautomers need Tier-2 review",
        },
    )


def check_box_cutoff(structure_path, *, rcoulomb: float = 1.0, min_ratio: float = 2.0) -> DiagnosticResult:
    """PME minimum-image sanity: the smallest box edge must be >= 2 x rcoulomb,
    otherwise a periodic image interacts with its own cutoff sphere."""
    import MDAnalysis as mda

    u = mda.Universe(str(structure_path))
    box = u.dimensions
    if box is None:
        raise ValueError("no periodic box in structure")
    edges = box[:3]
    min_edge = float(edges.min()) / 10.0
    ratio = min_edge / rcoulomb
    return DiagnosticResult(
        name="box_cutoff",
        passed=ratio >= min_ratio,
        threshold=float(min_ratio),
        value=float(ratio),
        detail={
            "min_box_edge_nm": min_edge,
            "rcoulomb_nm": float(rcoulomb),
            "ratio": float(ratio),
            "box_edges_nm": [float(e) / 10.0 for e in edges],
        },
    )


def check_steric_clashes(
    structure_path,
    *,
    threshold: float = 1.0,
    selection: str = "not name H*",
) -> DiagnosticResult:
    """Count heavy-atom pairs closer than `threshold` Angstrom.
    Real covalent bonds among heavy atoms are >= ~1.1 A, so a threshold of 1.0 A
    flags only genuinely overlapping (non-bonded) atoms. No bond-guessing needed,
    which keeps this robust across structures with virtual sites / DUMMY atoms."""
    import MDAnalysis as mda
    from MDAnalysis.lib.distances import self_capped_distance

    u = mda.Universe(str(structure_path))
    grp = u.select_atoms(selection)
    pairs, dists = self_capped_distance(
        grp.positions, min_cutoff=0.01, max_cutoff=threshold, box=u.dimensions
    )
    uni_idx = grp.atoms.indices
    clashes = [
        {"a": int(uni_idx[i]), "b": int(uni_idx[j]), "dist_A": float(d)}
        for (i, j), d in zip(pairs, dists)
    ]
    n = len(clashes)
    return DiagnosticResult(
        name="steric_clashes",
        passed=n == 0,
        threshold=0.0,
        value=float(n),
        detail={
            "n_clashes": n,
            "threshold_A": float(threshold),
            "selection": selection,
            "sample": clashes[:10],
        },
    )
