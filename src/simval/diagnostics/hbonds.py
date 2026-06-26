from __future__ import annotations

from simval.result import DiagnosticResult


def check_hydrogen_bonds(
    structure_path,
    trajectory_path,
    *,
    selection: str = "protein",
    min_count: float = 5.0,
) -> DiagnosticResult:
    """Protein hydrogen-bond inventory (informational + sanity). A folded protein
    with ~0 intramolecular H-bonds is suspect; surfaces the network for review."""
    import MDAnalysis as mda
    from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
    from collections import Counter

    u = mda.Universe(str(structure_path), str(trajectory_path))
    sel = f"{selection} and (name N or name O)"
    hb = HydrogenBondAnalysis(
        u, donors_sel=sel, acceptors_sel=sel, hydrogens_sel=f"{selection} and name H*")
    hb.run()
    n_frames = len(u.trajectory)
    if len(hb.results.hbonds) == 0:
        per_frame = [0] * n_frames
    else:
        frames = hb.results.hbonds[:, 0].astype(int)
        counts = Counter(frames)
        per_frame = [counts.get(f, 0) for f in range(n_frames)]
    mean = sum(per_frame) / max(len(per_frame), 1)
    return DiagnosticResult(
        name="hydrogen_bonds",
        passed=mean >= min_count,
        threshold=float(min_count),
        value=float(mean),
        detail={
            "mean_count": float(mean),
            "min": int(min(per_frame)) if per_frame else 0,
            "max": int(max(per_frame)) if per_frame else 0,
            "n_frames": int(n_frames),
            "scope": "intramolecular protein H-bonds (donors/acceptors in selection)",
        },
    )
