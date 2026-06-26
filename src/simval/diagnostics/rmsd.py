from __future__ import annotations

import numpy as np

from simval.result import DiagnosticResult


def kabsch_align(P: np.ndarray, Q: np.ndarray) -> np.ndarray:
    Pc = P - P.mean(axis=0)
    Qc = Q - Q.mean(axis=0)
    H = Pc.T @ Qc
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    return Pc @ R


def rmsd(P: np.ndarray, Q: np.ndarray) -> float:
    Qc = Q - Q.mean(axis=0)
    Pa = kabsch_align(P, Q)
    diff = Pa - Qc
    return float(np.sqrt(np.mean(np.sum(diff * diff, axis=1))))


def rmsd_over_time(positions: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return np.array([rmsd(positions[i], reference) for i in range(positions.shape[0])])


def check_rmsd_plateau(
    positions: np.ndarray,
    reference: np.ndarray,
    *,
    tail_fraction: float = 0.3,
    max_drift_fraction: float = 0.1,
    max_rmsd: float | None = None,
) -> DiagnosticResult:
    series = rmsd_over_time(positions, reference)
    n = series.size
    start = int(n * (1.0 - tail_fraction))
    tail = series[start:]
    x = np.arange(tail.size, dtype=float)
    slope = float(np.polyfit(x, tail, 1)[0]) if tail.size > 1 else 0.0
    mean_tail = float(tail.mean())
    drift_fraction = abs(slope) * tail.size / mean_tail if mean_tail > 0 else float("inf")
    passes_plateau = drift_fraction <= max_drift_fraction
    passes_level = (max_rmsd is None) or (mean_tail <= max_rmsd)
    return DiagnosticResult(
        name="rmsd_plateau",
        passed=bool(passes_plateau and passes_level),
        threshold=max_drift_fraction,
        value=float(drift_fraction),
        detail={
            "metric": "tail_drift_fraction",
            "mean_tail_rmsd_nm": mean_tail,
            "final_rmsd_nm": float(series[-1]),
            "tail_slope_nm_per_frame": slope,
            "tail_drift_fraction": float(drift_fraction),
            "passes_level": bool(passes_level),
            "max_rmsd_nm": max_rmsd,
            "tail_fraction": tail_fraction,
            "n_frames": int(n),
        },
    )
