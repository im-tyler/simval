"""Per-check thresholds, made explicit and overridable.

Defaults are starting points, not laws of physics (a flexible loop and a rigid
pocket need different RMSD ceilings). Override per-run via a `thresholds.json`
in the run-dir or the CLI `--thresholds` flag. Each check records the threshold
it actually used in its DiagnosticResult.

Externally supplied thresholds (run-dir file, CLI overrides) are validated
before use: finite, strictly positive, and under a sanity ceiling (audit
ORA-004) — a tol=inf/NaN override must never turn a bound into an always-pass.
"""
from __future__ import annotations

import json
import math
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

# Universal sanity ceiling for externally supplied thresholds: no simval
# check has a meaningful bound anywhere near this, so anything larger is a
# configuration error, not a tolerance.
MAX_THRESHOLD = 1e6

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


def validate_threshold(name: str, value) -> float:
    """Fail closed on non-finite, non-positive, or absurd thresholds.

    JSON parses `NaN`/`Infinity` literals into floats, so a thresholds file
    can smuggle in a bound that makes every `<= threshold` comparison true
    (inf) or vacuous (NaN). Reject those, negatives, zero, and anything
    above the sanity ceiling with a clear error (audit ORA-004).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"threshold {name!r} must be a number, got {value!r}") from None
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(f"threshold {name!r} must be finite, got {v!r}")
    if v <= 0:
        raise ValueError(f"threshold {name!r} must be strictly positive, got {v}")
    if v > MAX_THRESHOLD:
        raise ValueError(
            f"threshold {name!r} exceeds the sanity ceiling {MAX_THRESHOLD}: {v}"
        )
    return v


def load(run_dir=None, overrides: dict | None = None) -> dict:
    """Resolved thresholds = defaults <- run-dir thresholds.json <- overrides."""
    resolved = dict(DEFAULT_THRESHOLDS)
    if run_dir is not None:
        f = Path(run_dir) / "thresholds.json"
        if f.exists():
            raw = json.loads(f.read_text())
            if not isinstance(raw, dict):
                raise ValueError(f"thresholds file must be a JSON object: {f}")
            for k, v in raw.items():
                resolved[k] = validate_threshold(k, v)
    if overrides:
        if not isinstance(overrides, dict):
            raise ValueError("threshold overrides must be a JSON object")
        for k, v in overrides.items():
            resolved[k] = validate_threshold(k, v)
    return resolved


def kwargs_for(name: str, thresholds: dict) -> dict:
    """Map a check name + resolved thresholds to the kwargs that check accepts."""
    if name not in CHECK_KWARG:
        return {}
    return {CHECK_KWARG[name]: thresholds.get(name, DEFAULT_THRESHOLDS.get(name))}
