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

    Returns [] only for the typed not-available case: a .tpr this MDAnalysis
    build explicitly refuses (version skew — its TPR readers signal that with
    an IOError naming the tpr). Any other parse failure propagates instead of
    silently disabling ff_coverage (audit FF-001)."""
    import MDAnalysis as mda

    try:
        u = mda.Universe(str(top))
        grp = u.select_atoms(selection) if selection else u.atoms
        return list(grp.types)
    except IOError as e:
        msg = str(e)
        if "tpr" in msg.lower() or "gromacs" in msg.lower():
            return []
        raise


def load_atom_names(top, *, selection: str | None = None) -> list[str]:
    import MDAnalysis as mda

    u = mda.Universe(str(top))
    grp = u.select_atoms(selection) if selection else u.atoms
    return list(grp.names)


CONSERVED_ENERGY_ALIASES = (
    "Conserved-En.",
    "Conserved En.",
    "Conserved-En",
    "Total-Energy",
    "Total Energy",
)


def load_preferred_energy(path):
    """Return (term_name, array) for the conserved-energy column.

    Only explicit, labeled columns are accepted — the documented alias set
    above (GROMACS spellings of the conserved energy and the total energy).
    A file whose expected label is missing is an error, never a positional
    fallback to the first data column: an arbitrary column (temperature,
    box edge, pressure) is not a conserved quantity and silently drifts
    the verdict (audit IO-002).
    """
    cols = load_energy_xvg(path, column=None)
    for key in CONSERVED_ENERGY_ALIASES:
        if key in cols:
            return key, cols[key]
    raise ValueError(
        f"{path}: no conserved-energy column labeled {list(CONSERVED_ENERGY_ALIASES)} "
        f"(found: {sorted(k for k in cols if k != 'time')})"
    )


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
