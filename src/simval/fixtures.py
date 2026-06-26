from __future__ import annotations

import json
from pathlib import Path

import numpy as np


def good_energy_series(n: int = 1000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.full(n, -12345.0) + rng.normal(0.0, 2.0, size=n)


def drifting_energy_series(n: int = 1000, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.full(n, -12345.0) + rng.normal(0.0, 2.0, size=n) + np.linspace(0.0, 500.0, n)


def good_positions(n_frames: int = 500, n_atoms: int = 100, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.0, 5.0, (n_atoms, 3))
    osc = rng.normal(0.0, 0.01, (n_frames, n_atoms, 3))
    return base[None, :, :] + osc


def unfolding_positions(n_frames: int = 500, n_atoms: int = 100, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    base = rng.uniform(0.0, 5.0, (n_atoms, 3))
    steps = rng.normal(0.0, 0.006, (n_frames, n_atoms, 3))
    return base[None, :, :] + np.cumsum(steps, axis=0)


GOOD_ATOM_TYPES = ["C", "CA", "N", "O", "CB", "CG", "CD", "NE", "CZ", "NH1"]
BAD_ATOM_TYPES = GOOD_ATOM_TYPES + ["XX", "ZZ"]
FF_ATOM_TYPES = ["C", "CA", "N", "O", "CB", "CG", "CD", "NE", "CZ", "NH1", "H", "HA", "HB"]

GOOD_PARAMS = {
    "dt": {"value": 0.002, "unit": "ps"},
    "nsteps": {"value": 500000, "unit": ""},
    "ref_t": {"value": 300.0, "unit": "K"},
}

BAD_PARAMS = {
    "dt": {"value": 0.002, "unit": "K"},
    "nsteps": {"value": -100, "unit": ""},
    "ref_t": {"value": 300.0, "unit": "K"},
}


def make_run_dir(path, *, good: bool = True, seed: int = 42) -> Path:
    run = Path(path)
    run.mkdir(parents=True, exist_ok=True)
    np.save(run / "energy.npy", good_energy_series(seed=seed) if good else drifting_energy_series(seed=seed))
    pos = good_positions(seed=seed) if good else unfolding_positions(seed=seed)
    np.save(run / "positions.npy", pos)
    np.save(run / "reference.npy", pos[0])
    (run / "atom_types.txt").write_text("\n".join(GOOD_ATOM_TYPES if good else BAD_ATOM_TYPES) + "\n")
    (run / "ff_atom_types.txt").write_text("\n".join(FF_ATOM_TYPES) + "\n")
    (run / "params.json").write_text(json.dumps(GOOD_PARAMS if good else BAD_PARAMS, indent=2))
    return run
