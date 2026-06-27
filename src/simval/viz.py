"""Plot-data extraction for the web dashboard. Returns JSON-able time-series and
orbit arrays for any run-dir, dispatching by engine. UI-agnostic — a notebook
or agent could consume the same dict."""
from __future__ import annotations

from pathlib import Path


def series_for(run_dir, *, selection: str = "protein and name CA", max_points: int = 400) -> dict:
    from simval.context import select_engine
    from simval.diagnostics.rmsd import rmsd_over_time
    from simval.diagnostics.rmsf import per_residue_rmsf

    run = Path(run_dir)
    engine = select_engine(run)
    ctx = engine.load_context(run, selection)
    out: dict = {"engine": engine.name, "series": {}, "orbit": None, "field": None}

    if ctx.energy is not None:
        out["series"]["energy"] = _downsample(ctx.energy, max_points)

    if ctx.positions is not None and ctx.reference is not None:
        rseries = rmsd_over_time(ctx.positions, ctx.reference)
        out["series"]["rmsd_nm"] = _downsample(rseries, max_points)

    if ctx.ca_positions is not None and ctx.ca_reference is not None:
        rmsf = per_residue_rmsf(ctx.ca_positions, ctx.ca_reference)
        out["series"]["rmsf_nm"] = rmsf.tolist()

    # n-body orbit
    if "body_xy" in ctx.extra:
        body_xy = ctx.extra["body_xy"]
        out["orbit"] = [
            {"x": _downsample(body_xy[bi, :, 0], max_points),
             "y": _downsample(body_xy[bi, :, 1], max_points)}
            for bi in range(body_xy.shape[0])
        ]

    # GENERIC: any 1D array in ctx.extra -> series; any 2D -> field heatmap.
    # Makes ALL domains render automatically without per-domain code.
    import numpy as _np
    for key, val in ctx.extra.items():
        if isinstance(val, _np.ndarray):
            if val.ndim == 1 and val.size > 1 and key not in out["series"]:
                out["series"][key] = _downsample(val, max_points)
            elif val.ndim == 2 and out["field"] is None:
                out["field"] = _downsample_field(val, max_points)

    return out


def _downsample(arr, max_points):
    import numpy as np
    a = np.asarray(arr)
    if a.size <= max_points:
        return a.tolist()
    idx = np.linspace(0, a.size - 1, max_points).astype(int)
    return a[idx].tolist()


def _downsample_field(field, max_points):
    """field: (n_times, nx) -> downsample both axes to keep payload small."""
    import numpy as np
    if field is None:
        return None
    f = np.asarray(field, dtype=float)
    if f.ndim != 2:
        return None
    nt, nx = f.shape
    t_idx = np.linspace(0, nt - 1, min(nt, max_points)).astype(int)
    x_idx = np.linspace(0, nx - 1, min(nx, max_points)).astype(int)
    return f[t_idx][:, x_idx].tolist()


def _trajectory_files(run):
    from simval._util import find_files
    top = find_files(run, "*.gro", "*.pdb", "*.prmtop", "*.psf", "*.tpr")
    traj = find_files(run, "*.xtc", "*.dcd", "*.trr", "*.nc")
    return top, traj


def frame_count(run_dir) -> int:
    import MDAnalysis as mda
    top, traj = _trajectory_files(Path(run_dir))
    if not (top and traj):
        return 0
    u = mda.Universe(str(top), str(traj))
    return int(len(u.trajectory))


def structure_pdb(run_dir, frame: int = 0, selection: str = "protein") -> str:
    """Return a PDB string for `selection` at `frame` -- for 3D rendering."""
    import tempfile

    import MDAnalysis as mda
    top, traj = _trajectory_files(Path(run_dir))
    if not (top and traj):
        raise FileNotFoundError("run-dir has no MD trajectory to render")
    u = mda.Universe(str(top), str(traj))
    frame = max(0, min(frame, len(u.trajectory) - 1))
    u.trajectory[frame]
    grp = u.select_atoms(selection) if selection else u.atoms
    with tempfile.NamedTemporaryFile(suffix=".pdb", mode="w", delete=False) as f:
        path = f.name
    grp.write(path)
    pdb = Path(path).read_text()
    Path(path).unlink()
    return pdb
