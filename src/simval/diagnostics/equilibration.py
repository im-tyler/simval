from __future__ import annotations

import numpy as np

from simval.result import DiagnosticResult


def _autocorrelation(x: np.ndarray) -> np.ndarray:
    x = x - x.mean()
    n = x.size
    c = np.correlate(x, x, mode="full")[n - 1:]
    if c[0] == 0:
        return c
    return c / c[0]


def integrated_autocorr_time(x: np.ndarray, *, max_lag: int | None = None) -> float:
    acf = _autocorrelation(np.asarray(x, dtype=float))
    if max_lag is None:
        max_lag = acf.size
    tau = 0.0
    for k in range(1, min(max_lag, acf.size)):
        if acf[k] <= 0:
            break
        tau += acf[k]
    return 1.0 + 2.0 * tau


def effective_sample_size(x: np.ndarray, *, max_lag: int | None = None) -> float:
    n = np.asarray(x).size
    tau = integrated_autocorr_time(x, max_lag=max_lag)
    return n / tau if tau > 0 else float(n)


def equilibration_index(series: np.ndarray, *, window: int | None = None, tol: float = 0.05) -> int:
    s = np.asarray(series, dtype=float)
    n = s.size
    if window is None:
        window = max(10, n // 20)
    if n < 2 * window:
        return 0
    cumulative_mean = np.cumsum(s) / np.arange(1, n + 1)
    global_mean = s.mean()
    scale = abs(global_mean) + 1e-12
    for i in range(n - window):
        block = cumulative_mean[i : i + window]
        if np.all(np.abs(block - global_mean) / scale <= tol):
            return i
    return n - 1


def check_equilibration(
    series: np.ndarray,
    *,
    min_ess: float = 10.0,
    min_fraction_equilibrated: float = 0.5,
    window: int | None = None,
    tol: float = 0.05,
) -> DiagnosticResult:
    s = np.asarray(series, dtype=float)
    ess = effective_sample_size(s)
    eq_idx = equilibration_index(s, window=window, tol=tol)
    frac_eq = 1.0 - (eq_idx / s.size)
    passed = (ess >= min_ess) and (frac_eq >= min_fraction_equilibrated)
    return DiagnosticResult(
        name="equilibration",
        passed=bool(passed),
        threshold=float(min_ess),
        value=float(ess),
        detail={
            "effective_sample_size": float(ess),
            "equilibration_index": int(eq_idx),
            "fraction_equilibrated": float(frac_eq),
            "min_fraction_equilibrated": float(min_fraction_equilibrated),
            "n_samples": int(s.size),
        },
    )
