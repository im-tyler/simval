from __future__ import annotations

import numpy as np

from simval.result import DiagnosticResult


def check_energy_drift(
    energy: np.ndarray,
    *,
    threshold: float = 0.01,
    skip_fraction: float = 0.1,
) -> DiagnosticResult:
    e = np.asarray(energy, dtype=float)
    if e.size < 2:
        raise ValueError("energy must have at least 2 samples")
    if not 0.0 <= skip_fraction < 1.0:
        raise ValueError("skip_fraction must be in [0, 1)")

    start = int(e.size * skip_fraction)
    window = e[start:]
    emean = float(window.mean())
    if emean == 0.0:
        raise ValueError("mean energy is zero; cannot compute relative drift")

    relative_range = float((window.max() - window.min()) / abs(emean))
    idx = np.arange(window.size, dtype=float)
    slope = float(np.polyfit(idx, window, 1)[0])
    drift_over_run = float(slope * window.size / abs(emean))

    return DiagnosticResult(
        name="energy_drift",
        passed=relative_range <= threshold,
        threshold=threshold,
        value=relative_range,
        detail={
            "metric": "relative_range",
            "relative_range": relative_range,
            "slope_per_step": slope,
            "drift_over_run": drift_over_run,
            "skip_fraction": skip_fraction,
            "n_samples": int(e.size),
            "n_window": int(window.size),
            "mean_energy": emean,
        },
    )
