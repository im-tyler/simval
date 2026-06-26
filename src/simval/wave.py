"""Wave / PDE domain (1D scalar wave equation u_tt = c^2 u_xx via leapfrog FDTD).

Genuinely different physics from MD/N-body (hyperbolic PDE). Headline check is
the CFL stability condition c*dt/dx <= 1 -- the PDE analog of the MD box-cutoff
sanity check. Built-in FDTD reference solver (MEEP is the production wrap target
where its install is available)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_wave(cfg: dict, *, sample_every: int = 4) -> dict:
    c = float(cfg["c"])
    dx = float(cfg["dx"])
    dt = float(cfg["dt"])
    nx = int(cfg["nx"])
    n = int(cfg["n_steps"])
    cfl = c * dt / dx
    src = cfg.get("source", {})
    src_pos = int(src.get("pos", nx // 4))
    src_freq = float(src.get("freq", 0.1))
    src_on = int(src.get("n_on", max(1, n // 10)))

    u = np.zeros(nx)
    u_prev = np.zeros(nx)
    cfl2 = cfl * cfl
    energy = []
    times = []
    fields = []
    step = 0
    with np.errstate(over="ignore", invalid="ignore"):
        while step < n:
            u_new = np.zeros(nx)
            u_new[1:-1] = (2 * u[1:-1] - u_prev[1:-1]
                           + cfl2 * (u[2:] - 2 * u[1:-1] + u[:-2]))
            if step < src_on:
                u_new[src_pos] += np.sin(2 * np.pi * src_freq * step * dt)
            if step % sample_every == 0:
                du_dt = (u_new - u_prev) / (2 * dt)
                du_dx = np.zeros(nx)
                du_dx[1:-1] = (u[2:] - u[:-2]) / (2 * dx)
                ke = 0.5 * np.sum(du_dt ** 2) * dx
                pe = 0.5 * (c ** 2) * np.sum(du_dx ** 2) * dx
                energy.append(float(ke + pe))
                times.append(step * dt)
                fields.append(u.copy())
            u_prev = u
            u = u_new
            step += 1
    return {
        "times": np.array(times),
        "energy": np.array(energy),
        "fields": np.array(fields),
        "cfl": float(cfl),
        "src_on": src_on,
        "nx": nx,
        "n_steps": n,
    }


def check_cfl(cfl: float, *, max_cfl: float = 1.0) -> DiagnosticResult:
    return DiagnosticResult(
        name="cfl_stability",
        passed=cfl <= max_cfl,
        threshold=float(max_cfl),
        value=float(cfl),
        detail={"cfl": float(cfl), "rule": "c*dt/dx <= 1 required for leapfrog stability"},
    )


def check_wave_energy(energy, *, src_on_index: int = 0, max_growth: float = 1.25) -> DiagnosticResult:
    """After the source turns off, total wave energy must stay bounded.
    Exponential growth flags a numerically unstable scheme."""
    e = np.asarray(energy, dtype=float)
    tail_start = max(src_on_index, 1)
    tail = e[tail_start:] if e.size > tail_start else e
    base = float(np.abs(tail[:max(1, len(tail) // 4)]).mean()) + 1e-15
    growth = float(np.abs(tail).max() / base)
    return DiagnosticResult(
        name="wave_energy_bounded",
        passed=growth <= max_growth,
        threshold=float(max_growth),
        value=growth,
        detail={"energy_growth": growth, "n_samples": int(e.size)},
    )


class WaveEngine(EngineAdapter):
    name = "wave-fdtd"

    def detect(self, run: Path) -> bool:
        return (run / "wave.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "wave.json").read_text())
        data = integrate_wave(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {
            "wave_energy": data["energy"],
            "cfl": data["cfl"],
            "src_on_index": int(data["src_on"] // 4),
            "times": data["times"],
            "field": data["fields"],
        }
        ctx.run_params = {
            "engine": self.name,
            "domain": "wave-pde",
            "cfl": data["cfl"],
            "nx": data["nx"],
            "n_steps": data["n_steps"],
        }
        return ctx


register_engine(WaveEngine())
