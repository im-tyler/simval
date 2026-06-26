"""Per-check thresholds, made explicit and overridable.

Defaults are starting points, not laws of physics (a flexible loop and a rigid
pocket need different RMSD ceilings). Override per-run via a `thresholds.json`
in the run-dir or the CLI `--thresholds` flag. Each check records the threshold
it actually used in its DiagnosticResult.
"""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_THRESHOLDS: dict[str, float] = {
    "energy_drift": 0.01,
    "rmsd_plateau": 0.1,
    "structural_equilibration": 10.0,
    "per_residue_rmsf": 0.3,
    "box_cutoff": 2.0,
    "charge_state": 0.5,
    "hydrogen_bonds": 5.0,
    "angular_momentum": 1e-4,
    "com_drift": 1e-3,
    "cfl_stability": 1.0,
    "wave_energy_bounded": 1.25,
}

CHECK_KWARG = {
    "energy_drift": "threshold",
    "rmsd_plateau": "max_drift_fraction",
    "structural_equilibration": "min_ess",
    "per_residue_rmsf": "threshold_nm",
    "box_cutoff": "min_ratio",
    "charge_state": "tol",
    "hydrogen_bonds": "min_count",
    "angular_momentum": "threshold",
    "com_drift": "threshold",
    "cfl_stability": "max_cfl",
    "wave_energy_bounded": "max_growth",
}


def load(run_dir=None, overrides: dict | None = None) -> dict:
    """Resolved thresholds = defaults <- run-dir thresholds.json <- overrides."""
    resolved = dict(DEFAULT_THRESHOLDS)
    if run_dir is not None:
        f = Path(run_dir) / "thresholds.json"
        if f.exists():
            resolved.update({k: float(v) for k, v in json.loads(f.read_text()).items()})
    if overrides:
        resolved.update({k: float(v) for k, v in overrides.items()})
    return resolved


def kwargs_for(name: str, thresholds: dict) -> dict:
    """Map a check name + resolved thresholds to the kwargs that check accepts."""
    if name not in CHECK_KWARG:
        return {}
    return {CHECK_KWARG[name]: thresholds.get(name, DEFAULT_THRESHOLDS.get(name))}
