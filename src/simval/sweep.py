from __future__ import annotations

from pathlib import Path

from simval.oracle.validate import compute_metrics


def sweep(folder, *, selection: str = "protein and name CA", baseline: str | None = None) -> dict:
    """Diagnose every run-dir under `folder` and tabulate key metrics.
    The parameter-sweep daily loop: N runs compared at a glance."""
    root = Path(folder)
    run_dirs = sorted(d for d in root.iterdir() if d.is_dir())
    rows = []
    for d in run_dirs:
        try:
            m = compute_metrics(d, selection=selection)
            m = {k: v for k, v in m.items() if isinstance(v, (int, float))}
            m["run"] = d.name
            rows.append(m)
        except Exception as e:
            rows.append({"run": d.name, "_error": str(e)[:100]})

    base = None
    if baseline is not None:
        try:
            base = {k: v for k, v in compute_metrics(baseline, selection=selection).items()
                    if isinstance(v, (int, float))}
        except Exception:
            base = None

    return {"runs": rows, "baseline": base, "n": len(rows)}


KEY_METRICS = [
    "mean_rmsd_nm", "final_rmsd_nm", "mean_rg_nm",
    "energy_relative_range", "cfl", "energy_growth",
    "angular_momentum_relative_range",
]
