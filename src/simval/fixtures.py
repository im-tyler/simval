from __future__ import annotations

import numpy as np


def good_energy_series(n: int = 1000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.full(n, -12345.0) + rng.normal(0.0, 2.0, size=n)


def drifting_energy_series(n: int = 1000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.full(n, -12345.0) + rng.normal(0.0, 2.0, size=n) + np.linspace(0.0, 500.0, n)
