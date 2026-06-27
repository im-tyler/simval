"""Relativistic dynamics domain (charged particle in E/B fields, Boris pusher).

The 12th physics domain. The Boris algorithm is the standard relativistic
particle pusher for PIC codes. Invariant: relativistic energy gamma*mc^2 is
conserved for static electromagnetic fields."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_relativistic(cfg: dict) -> dict:
    m = float(cfg["mass"])
    q = float(cfg["charge"])
    c = float(cfg.get("c", 1.0))
    E = np.array(cfg.get("E", [0.0, 0.0, 0.0]), dtype=float)
    B = np.array(cfg.get("B", [0.0, 0.0, 1.0]), dtype=float)
    dt = float(cfg["dt"])
    n = int(cfg["n_steps"])
    p = np.array(cfg.get("initial_momentum", [0.1, 0.0, 0.0]), dtype=float)

    gamma_history = []
    with np.errstate(over="ignore", invalid="ignore"):
        for _ in range(n):
            gamma = np.sqrt(1.0 + (p @ p) / (m * c) ** 2)
            gamma_history.append(float(gamma))
            p / (gamma * m)
            t_half = q * B * dt / (2.0 * gamma * m)
            s = 2.0 * t_half / (1.0 + t_half @ t_half)
            p_minus = p + q * E * dt / 2.0
            p_prime = p_minus + np.cross(p_minus, t_half)
            p_plus = p_minus + np.cross(p_prime, s)
            p = p_plus + q * E * dt / 2.0
    return {"gamma": np.array(gamma_history), "final_gamma": float(np.sqrt(1.0 + (p @ p) / (m * c) ** 2)),
            "dt": dt, "n_steps": n}


def check_relativistic_energy(gamma, *, max_drift: float = 1e-3) -> DiagnosticResult:
    g = np.asarray(gamma, dtype=float)
    mean = float(np.abs(g).mean()) + 1e-15
    drift = float((g.max() - g.min()) / mean)
    return DiagnosticResult(
        name="relativistic_energy",
        passed=drift <= max_drift,
        threshold=float(max_drift),
        value=drift,
        detail={"gamma_drift": drift, "mean_gamma": float(g.mean())},
    )


class RelativisticEngine(EngineAdapter):
    name = "relativistic-boris"

    def detect(self, run: Path) -> bool:
        return (run / "relativistic.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "relativistic.json").read_text())
        data = integrate_relativistic(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"gamma": data["gamma"]}
        ctx.run_params = {"engine": self.name, "domain": "relativistic-dynamics",
                          "n_steps": data["n_steps"], "final_gamma": data["final_gamma"]}
        return ctx


register_engine(RelativisticEngine())
