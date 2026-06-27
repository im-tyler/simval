"""Quantum domain (statevector spin-1/2 dynamics).

The 6th physics domain. Evolves |psi> under a Hamiltonian via exact
diagonalisation (unitary). Invariant: norm conservation <psi|psi> = 1
(unitarity); populations oscillate (Rabi). Numpy-only; Qiskit is the production
wrap target for circuit-based work."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult

_SX = np.array([[0, 1], [1, 0]], dtype=complex)
_SZ = np.array([[1, 0], [0, -1]], dtype=complex)


def evolve_spin(cfg: dict) -> dict:
    w0 = float(cfg["omega0"])
    w1 = float(cfg["omega1"])
    dt = float(cfg["dt"])
    n = int(cfg["n_steps"])
    H = 0.5 * (w0 * _SZ + w1 * _SX)
    eig, V = np.linalg.eig(H)
    U = V @ np.diag(np.exp(-1j * eig * dt)) @ np.linalg.inv(V)
    psi = np.array([1.0 + 0j, 0.0 + 0j])
    norm = np.empty(n)
    p_up = np.empty(n)
    for k in range(n):
        psi = U @ psi
        norm[k] = float((np.abs(psi) ** 2).sum())
        p_up[k] = float(np.abs(psi[0]) ** 2)
    return {"norm": norm, "p_up": p_up, "dt": dt, "omega0": w0, "omega1": w1, "n_steps": n}


def check_norm_conservation(norm, *, max_drift: float = 1e-6) -> DiagnosticResult:
    nm = np.asarray(norm, dtype=float)
    drift = float(np.max(np.abs(nm - 1.0)))
    return DiagnosticResult(
        name="norm_conservation",
        passed=drift <= max_drift,
        threshold=float(max_drift),
        value=drift,
        detail={"max_deviation_from_1": drift, "mean": float(nm.mean())},
    )


def check_rabi_oscillates(p_up, *, min_swing: float = 0.1) -> DiagnosticResult:
    """Sanity: a driven spin should actually flip (population must swing),
    not stay frozen -- flags a misparameterised drive."""
    p = np.asarray(p_up, dtype=float)
    swing = float(p.max() - p.min())
    return DiagnosticResult(
        name="rabi_population_swing",
        passed=swing >= min_swing,
        threshold=float(min_swing),
        value=swing,
        detail={"population_swing": swing, "p_up_min": float(p.min()), "p_up_max": float(p.max())},
    )


class QuantumEngine(EngineAdapter):
    name = "quantum-spin"

    def detect(self, run: Path) -> bool:
        return (run / "quantum.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "quantum.json").read_text())
        data = evolve_spin(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"norm": data["norm"], "p_up": data["p_up"]}
        ctx.run_params = {"engine": self.name, "domain": "quantum",
                          "omega0": data["omega0"], "omega1": data["omega1"], "n_steps": data["n_steps"]}
        return ctx


register_engine(QuantumEngine())
