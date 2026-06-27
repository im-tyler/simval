"""Electromagnetism domain (2D TMz Maxwell FDTD, the Yee algorithm).

The 5th physics domain. Coupled E/H vector fields (genuinely distinct from the
scalar wave). Invariants: the Courant stability condition
  c*dt*sqrt(1/dx^2 + 1/dy^2) <= 1
and EM energy boundedness  0.5*(eps*|E|^2 + mu*|H|^2)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_em(cfg: dict, *, sample_every: int = 10) -> dict:
    c = float(cfg.get("c", 1.0))
    dx = float(cfg["dx"])
    dy = float(cfg["dy"])
    dt = float(cfg["dt"])
    nx = int(cfg["nx"])
    ny = int(cfg["ny"])
    n = int(cfg["n_steps"])
    eps = mu = 1.0
    src = cfg.get("source", {})
    sx, sy = int(src.get("x", nx // 2)), int(src.get("y", ny // 2))
    freq = float(src.get("freq", 0.1))
    on = int(src.get("n_on", n // 8))

    Ez = np.zeros((nx, ny))
    Hx = np.zeros((nx, ny))
    Hy = np.zeros((nx, ny))
    Cb = dt / (mu * dx)
    Cd = dt / (eps * dx)
    energy = []
    fields = []
    with np.errstate(over="ignore", invalid="ignore"):
        for step in range(n):
            Hx[:, 1:-1] -= Cb * (Ez[:, 2:] - Ez[:, :-2]) / 2.0
            Hy[1:-1, :] += Cb * (Ez[2:, :] - Ez[:-2, :]) / 2.0
            Ez[1:-1, 1:-1] += Cd * ((Hy[2:, 1:-1] - Hy[:-2, 1:-1]) / 2.0
                                    - (Hx[1:-1, 2:] - Hx[1:-1, :-2]) / 2.0)
            if step < on:
                Ez[sx, sy] += np.sin(2 * np.pi * freq * step * dt)
            if step % sample_every == 0:
                energy.append(float(0.5 * (eps * (Ez**2).sum() + mu * (Hx**2 + Hy**2).sum())))
                fields.append((Ez**2).copy())
    courant = c * dt * np.sqrt(1.0 / dx**2 + 1.0 / dy**2)
    field = np.array(fields[-1]) if fields else np.zeros((nx, ny))
    return {"energy": np.array(energy), "courant": float(courant), "field": field,
            "nx": nx, "ny": ny, "n_steps": n, "src_on": on}


def check_courant(courant: float, *, max_courant: float = 1.0) -> DiagnosticResult:
    return DiagnosticResult(
        name="em_courant",
        passed=courant <= max_courant,
        threshold=float(max_courant),
        value=float(courant),
        detail={"courant": float(courant), "rule": "c*dt*sqrt(1/dx^2+1/dy^2) <= 1 (2D Yee)"},
    )


def check_em_energy(energy, *, src_on_index: int = 0, max_growth: float = 1.25) -> DiagnosticResult:
    e = np.asarray(energy, dtype=float)
    tail_start = max(src_on_index, 1)
    tail = e[tail_start:] if e.size > tail_start else e
    base = float(np.abs(tail[:max(1, len(tail) // 4)]).mean()) + 1e-15
    growth = float(np.abs(tail).max() / base)
    return DiagnosticResult(
        name="em_energy_bounded",
        passed=growth <= max_growth,
        threshold=float(max_growth),
        value=growth,
        detail={"energy_growth": growth},
    )


class EMEngine(EngineAdapter):
    name = "em-fdtd"

    def detect(self, run: Path) -> bool:
        return (run / "em.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "em.json").read_text())
        data = integrate_em(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {
            "em_energy": data["energy"], "courant": data["courant"],
            "field": data["field"], "src_on_index": int(data["src_on"] // 10),
        }
        ctx.run_params = {"engine": self.name, "domain": "electromagnetism",
                          "courant": data["courant"], "nx": data["nx"], "ny": data["ny"]}
        return ctx


register_engine(EMEngine())
