from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_XVG_LEGEND = re.compile(r'@\s*s(\d+)\s+legend\s+"([^"]+)"')


def load_trajectory(xtc, top, *, selection: str = "protein"):
    """Load a GROMACS trajectory + topology via MDAnalysis.

    selection: MDAnalysis atom-selection (default 'protein'). Selecting the protein
    (or 'protein and name CA') avoids PBC/water artifacts that corrupt naive RMSD.
    Returns (positions_nm [n_frames, n_atoms, 3], reference_nm, atom_names).
    Units converted from MDAnalysis Angstrom to GROMACS nanometres.
    """
    import MDAnalysis as mda

    u = mda.Universe(str(top), str(xtc))
    grp = u.select_atoms(selection) if selection else u.atoms
    frames = np.stack([grp.positions.copy() for ts in u.trajectory]) / 10.0
    return frames, frames[0].copy(), list(grp.names)


def load_atom_types(top, *, selection: str = "protein") -> list[str]:
    """Force-field atom types from a topology that carries them (e.g. .tpr).
    Returns [] if the topology can't be parsed (e.g. tpx version skew)."""
    try:
        import MDAnalysis as mda

        u = mda.Universe(str(top))
        grp = u.select_atoms(selection) if selection else u.atoms
        return list(grp.types)
    except Exception:
        return []


def load_atom_names(top, *, selection: str | None = None) -> list[str]:
    import MDAnalysis as mda

    u = mda.Universe(str(top))
    grp = u.select_atoms(selection) if selection else u.atoms
    return list(grp.names)


def load_preferred_energy(path):
    """Return (term_name, array) — the conserved-energy column if present
    (correct for thermostatted/NVT runs), else the first non-time column."""
    cols = load_energy_xvg(path, column=None)
    for key in ("Conserved-En.", "Conserved En.", "Conserved-En", "Total-Energy", "Total Energy"):
        if key in cols:
            return key, cols[key]
    name, arr = next((k, v) for k, v in cols.items() if k != "time")
    return name, arr


def load_residue_labels(top, *, selection: str = "protein and name CA") -> list[str]:
    """Per-atom residue labels like 'ALA17' for the given selection (one per atom)."""
    import MDAnalysis as mda

    u = mda.Universe(str(top))
    grp = u.select_atoms(selection)
    return [f"{r.resname}{r.resnum}" for r in grp.residues]


def load_energy_xvg(path, *, column: int | None = 1):
    """Parse a GROMACS xmgrace .xvg energy file.

    column: 1-indexed data column to return (0 = x/time). None -> {legend: array}.
    """
    legends: dict[int, str] = {}
    rows: list[list[float]] = []
    for ln in Path(path).read_text().splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("@"):
            m = _XVG_LEGEND.match(s)
            if m:
                legends[int(m.group(1)) + 1] = m.group(2)
            continue
        parts = s.split()
        try:
            rows.append([float(x) for x in parts])
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"no numeric data in {path}")
    arr = np.array(rows, dtype=float)
    if column is None:
        out = {legends.get(i, f"col{i}"): arr[:, i] for i in range(1, arr.shape[1])}
        out["time"] = arr[:, 0]
        return out
    if column >= arr.shape[1]:
        raise ValueError(f"column {column} out of range (file has {arr.shape[1]} cols)")
    return arr[:, column]
