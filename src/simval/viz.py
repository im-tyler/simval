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
    out: dict = {"engine": engine.name, "series": {}, "orbit": None}

    if ctx.energy is not None:
        out["series"]["energy"] = _downsample(ctx.energy, max_points)

    if ctx.positions is not None and ctx.reference is not None:
        rseries = rmsd_over_time(ctx.positions, ctx.reference)
        out["series"]["rmsd_nm"] = _downsample(rseries, max_points)

    if ctx.ca_positions is not None and ctx.ca_reference is not None:
        rmsf = per_residue_rmsf(ctx.ca_positions, ctx.ca_reference)
        out["series"]["rmsf_nm"] = rmsf.tolist()

    if "L_magnitude" in ctx.extra:
        out["series"]["angular_momentum"] = _downsample(ctx.extra["L_magnitude"], max_points)
        out["series"]["com_drift"] = _downsample(
            __import__("numpy").sqrt(((ctx.extra["com"] - ctx.extra["com"][0]) ** 2).sum(axis=1)),
            max_points,
        )
        body_xy = ctx.extra["body_xy"]
        out["orbit"] = [
            {"x": _downsample(body_xy[bi, :, 0], max_points),
             "y": _downsample(body_xy[bi, :, 1], max_points)}
            for bi in range(body_xy.shape[0])
        ]
    return out


def _downsample(arr, max_points):
    import numpy as np
    a = np.asarray(arr)
    if a.size <= max_points:
        return a.tolist()
    idx = np.linspace(0, a.size - 1, max_points).astype(int)
    return a[idx].tolist()
