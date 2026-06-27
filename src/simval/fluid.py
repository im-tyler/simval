"""Fluids / CFD domain (2D Lattice Boltzmann, D2Q9, BGK collision).

The 4th physics domain through the same port. LBM is mesoscopic CFD; its natural
invariant is exact mass conservation (collision + periodic streaming both
conserve total density), and its stability condition is tau > 0.5 (the fluid
analogue of the wave CFL). Built-in reference solver (OpenFOAM is the production
wrap target)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult

# D2Q9 lattice: 9 velocity directions (ex, ey) and weights
_E = np.array([
    [0, 0], [1, 0], [0, 1], [-1, 0], [0, -1],
    [1, 1], [-1, 1], [-1, -1], [1, -1],
], dtype=float)
_W = np.array([4.0 / 9.0] + [1.0 / 9.0] * 4 + [1.0 / 36.0] * 4)


def integrate_fluid(cfg: dict, *, sample_every: int = 25) -> dict:
    nx, ny = int(cfg["nx"]), int(cfg["ny"])
    n = int(cfg["n_steps"])
    tau = float(cfg["tau"])
    rho0 = float(cfg.get("rho0", 1.0))
    rng = np.random.default_rng(int(cfg.get("seed", 0)))

    rho = rho0 + 0.01 * rng.standard_normal((nx, ny))
    ux = np.zeros((nx, ny))
    uy = np.zeros((nx, ny))
    f = np.empty((9, nx, ny))
    for i in range(9):
        cu = _E[i, 0] * ux + _E[i, 1] * uy
        f[i] = _W[i] * rho * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * (ux * ux + uy * uy))

    mass = []
    last_density = rho.copy()
    ex = _E[:, 0]
    ey = _E[:, 1]
    for step in range(n):
        rho = f.sum(axis=0)
        ux = (f * ex[:, None, None]).sum(axis=0) / rho
        uy = (f * ey[:, None, None]).sum(axis=0) / rho
        u2 = ux * ux + uy * uy
        for i in range(9):
            cu = ex[i] * ux + ey[i] * uy
            feq = _W[i] * rho * (1.0 + 3.0 * cu + 4.5 * cu * cu - 1.5 * u2)
            f[i] += (feq - f[i]) / tau
        for i in range(1, 9):
            f[i] = np.roll(f[i], (int(ex[i]), int(ey[i])), axis=(0, 1))
        if step % sample_every == 0:
            mass.append(float(rho.sum()))
            last_density = rho.copy()
    return {
        "mass": np.array(mass),
        "tau": tau,
        "density": last_density,
        "nx": nx, "ny": ny, "n_steps": n,
    }


def check_tau_stability(tau: float, *, min_tau: float = 0.5, max_tau: float = 2.0) -> DiagnosticResult:
    passed = min_tau < tau <= max_tau
    return DiagnosticResult(
        name="lbm_tau_stability",
        passed=passed,
        threshold=float(min_tau),
        value=float(tau),
        detail={"tau": float(tau), "min_tau": min_tau, "max_tau": max_tau,
                "kinematic_viscosity": float((tau - 0.5) / 3.0),
                "rule": "BGK stability requires 0.5 < tau (~2); nu = (tau-0.5)/3"},
    )


def check_mass_conservation(mass, *, max_drift: float = 1e-3) -> DiagnosticResult:
    m = np.asarray(mass, dtype=float)
    mean = float(np.abs(m).mean()) + 1e-15
    drift = float((m.max() - m.min()) / mean)
    return DiagnosticResult(
        name="mass_conservation",
        passed=drift <= max_drift,
        threshold=float(max_drift),
        value=drift,
        detail={"relative_drift": drift, "mean_mass": float(m.mean())},
    )


class FluidEngine(EngineAdapter):
    name = "fluid-lbm"

    def detect(self, run: Path) -> bool:
        return (run / "fluid.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "fluid.json").read_text())
        data = integrate_fluid(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {
            "mass": data["mass"],
            "tau": data["tau"],
            "field": data["density"],  # 2D density -> reuses the heatmap renderer
            "nx": data["nx"], "ny": data["ny"],
        }
        ctx.run_params = {
            "engine": self.name, "domain": "fluid-cfd",
            "tau": data["tau"], "nx": data["nx"], "ny": data["ny"],
            "n_steps": data["n_steps"],
        }
        return ctx


register_engine(FluidEngine())
