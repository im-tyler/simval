from __future__ import annotations

import numpy as np

from simval.result import DiagnosticResult


def _align_to_reference(positions: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Per-frame Kabsch alignment of each frame onto `reference` (both centered).
    Returns aligned coordinates centered at the reference centroid."""
    ref_c = reference - reference.mean(axis=0)
    out = np.empty_like(positions)
    for f in range(positions.shape[0]):
        P = positions[f]
        Pc = P - P.mean(axis=0)
        H = Pc.T @ ref_c
        U, _, Vt = np.linalg.svd(H)
        d = np.sign(np.linalg.det(Vt.T @ U.T))
        R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
        out[f] = Pc @ R
    return out


def per_residue_rmsf(positions: np.ndarray, reference: np.ndarray) -> np.ndarray:
    """Per-atom RMSF (nm) after aligning each frame to `reference`.
    Pass CA positions (one per residue) for per-residue mobility."""
    aligned = _align_to_reference(positions, reference)
    mean_pos = aligned.mean(axis=0)
    return np.sqrt(((aligned - mean_pos) ** 2).sum(axis=2).mean(axis=0))


def check_rmsf(
    positions: np.ndarray,
    reference: np.ndarray,
    *,
    labels: list[str] | None = None,
    threshold_nm: float = 0.3,
) -> DiagnosticResult:
    """Flag residues with RMSF above `threshold_nm` (flexible / ill-equilibrated regions)."""
    rmsf = per_residue_rmsf(positions, reference)
    n = rmsf.size
    high_idx = [i for i in range(n) if rmsf[i] > threshold_nm]
    high = [
        {"label": labels[i] if labels else str(i), "index": i, "rmsf_nm": float(rmsf[i])}
        for i in high_idx
    ]
    ranked = sorted(
        [{"label": labels[i] if labels else str(i), "index": i, "rmsf_nm": float(rmsf[i])}
         for i in range(n)],
        key=lambda r: r["rmsf_nm"], reverse=True,
    )[:10]
    return DiagnosticResult(
        name="per_residue_rmsf",
        passed=len(high) == 0,
        threshold=float(threshold_nm),
        value=float(rmsf.max()),
        detail={
            "mean_rmsf_nm": float(rmsf.mean()),
            "max_rmsf_nm": float(rmsf.max()),
            "n_above_threshold": len(high),
            "threshold_nm": float(threshold_nm),
            "high_mobility": high[:20],
            "top10": ranked,
            "n_residues": int(n),
        },
    )
