"""Heat transfer / diffusion domain (1D diffusion equation, explicit FDTD).

The 11th physics domain. dT/dt = alpha * d2T/dx2 via explicit finite differences.
Invariant: total heat energy (sum of T) conserved for insulated boundaries.
Stability: Fourier number alpha*dt/dx^2 <= 0.5 (the diffusion CFL)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_diffusion(cfg: dict, *, sample_every: int = 10) -> dict:
    alpha = float(cfg["alpha"])
    dx = float(cfg["dx"])
    dt = float(cfg["dt"])
    nx = int(cfg["nx"])
    n = int(cfg["n_steps"])
    T = np.zeros(nx)
    T[nx // 4: nx // 2] = 1.0  # initial hot patch
    fourier = alpha * dt / (dx * dx)
    energy = []
    fields = []
    with np.errstate(over="ignore", invalid="ignore"):
        for step in range(n):
            T_new = T.copy()
            T_new[1:-1] += fourier * (T[2:] - 2 * T[1:-1] + T[:-2])
            T_new[0] = T_new[1]      # zero-flux (insulated) left
            T_new[-1] = T_new[-2]    # zero-flux (insulated) right
            T = T_new
            if step % sample_every == 0:
                energy.append(float(T.sum()))
                fields.append(T.copy())
    return {"energy": np.array(energy), "fourier": float(fourier),
            "field": fields[-1] if fields else T, "nx": nx, "n_steps": n}


def check_fourier_stability(fourier: float, *, max_fourier: float = 0.5) -> DiagnosticResult:
    return DiagnosticResult(
        name="diffusion_fourier",
        passed=fourier <= max_fourier,
        threshold=float(max_fourier),
        value=float(fourier),
        detail={"fourier": float(fourier), "rule": "alpha*dt/dx^2 <= 0.5 for explicit stability"},
    )


def check_heat_conservation(energy, *, max_drift: float = 0.05) -> DiagnosticResult:
    e = np.asarray(energy, dtype=float)
    mean = float(np.abs(e).mean()) + 1e-15
    drift = float((e.max() - e.min()) / mean)
    return DiagnosticResult(
        name="heat_conservation",
        passed=drift <= max_drift,
        threshold=float(max_drift),
        value=drift,
        detail={"energy_drift": drift},
    )


class DiffusionEngine(EngineAdapter):
    name = "heat-diffusion"

    def detect(self, run: Path) -> bool:
        return (run / "diffusion.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "diffusion.json").read_text())
        data = integrate_diffusion(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"fourier": data["fourier"], "heat_energy": data["energy"],
                     "field": data["field"]}
        ctx.run_params = {"engine": self.name, "domain": "heat-transfer",
                          "fourier": data["fourier"], "nx": data["nx"]}
        return ctx


register_engine(DiffusionEngine())
