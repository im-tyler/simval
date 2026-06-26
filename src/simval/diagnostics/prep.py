from __future__ import annotations

from simval.result import DiagnosticResult


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
