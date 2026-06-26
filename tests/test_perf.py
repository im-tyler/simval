import time

import numpy as np

from simval.diagnostics.equilibration import check_equilibration
from simval.diagnostics.energy import check_energy_drift
from simval.diagnostics.rmsd import check_rmsd_plateau, rmsd_over_time


def test_large_inputs_complete_quickly():
    rng = np.random.default_rng(0)
    energy = np.full(50_000, -1000.0) + rng.normal(0.0, 5.0, 50_000)
    n_frames, n_atoms = 400, 2000
    positions = rng.uniform(0.0, 5.0, (n_frames, n_atoms, 3))

    t0 = time.time()
    e = check_energy_drift(energy)
    rseries = rmsd_over_time(positions, positions[0])
    r = check_rmsd_plateau(positions, positions[0])
    q = check_equilibration(rseries)
    elapsed = time.time() - t0

    assert isinstance(e.passed, bool)
    assert isinstance(r.passed, bool)
    assert isinstance(q.passed, bool)
    assert elapsed < 15.0, f"diagnostics too slow on large input: {elapsed:.1f}s"
