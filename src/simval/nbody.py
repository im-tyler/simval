"""N-body / celestial-mechanics domain. Proves the EngineAdapter port accepts a
genuinely different physics domain (gravity, not MD): reuses the universal
energy-conservation check (check_energy_drift) and adds its own invariants."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_system(system_path, *, samples: int = 200) -> dict:
    """Integrate a system.json with REBOUND and sample conserved quantities."""
    import rebound

    cfg = json.loads(Path(system_path).read_text())
    sim = rebound.Simulation()
    sim.dt = cfg.get("dt", 0.01)
    sim.G = cfg.get("G", 1.0)
    for body in cfg["bodies"]:
        pos = body["position"]
        vel = body["velocity"]
        sim.add(m=body["mass"], x=pos[0], y=pos[1], z=pos[2], vx=vel[0], vy=vel[1], vz=vel[2])
    sim.move_to_com()

    tmax = cfg.get("tmax", 10.0)
    times = np.linspace(0.0, tmax, samples)
    energy = np.empty(samples)
    Lmag = np.empty(samples)
    com = np.empty((samples, 3))
    for i, t in enumerate(times):
        sim.integrate(t)
        energy[i] = sim.energy()
        ps = sim.particles
        M = sum(p.m for p in ps)
        lx = ly = lz = 0.0
        cx = cy = cz = 0.0
        for p in ps:
            lx += p.m * (p.y * p.vz - p.z * p.vy)
            ly += p.m * (p.z * p.vx - p.x * p.vz)
            lz += p.m * (p.x * p.vy - p.y * p.vx)
            cx += p.m * p.x
            cy += p.m * p.y
            cz += p.m * p.z
        Lmag[i] = float(np.sqrt(lx * lx + ly * ly + lz * lz))
        com[i] = [cx / M, cy / M, cz / M]
    return {"times": times, "energy": energy, "L_magnitude": Lmag, "com": com}


def check_angular_momentum(L, *, threshold: float = 1e-4) -> DiagnosticResult:
    mean = float(np.abs(L).mean()) + 1e-15
    rel = float((L.max() - L.min()) / mean)
    return DiagnosticResult(
        name="angular_momentum",
        passed=rel <= threshold,
        threshold=float(threshold),
        value=rel,
        detail={"relative_range": rel, "mean": float(L.mean())},
    )


def check_com_drift(com, *, threshold: float = 1e-3) -> DiagnosticResult:
    d0 = com[0]
    drift = np.sqrt(((com - d0) ** 2).sum(axis=1))
    mx = float(drift.max())
    return DiagnosticResult(
        name="com_drift",
        passed=mx <= threshold,
        threshold=float(threshold),
        value=mx,
        detail={"max_drift": mx, "final_drift": float(drift[-1])},
    )


class ReboundEngine(EngineAdapter):
    name = "nbody-rebound"

    def detect(self, run: Path) -> bool:
        return (run / "system.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        data = integrate_system(run / "system.json")
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.energy = data["energy"]
        ctx.extra = {
            "L_magnitude": data["L_magnitude"],
            "com": data["com"],
            "times": data["times"],
        }
        ctx.run_params = {
            "engine": self.name,
            "n_samples": int(data["energy"].size),
            "domain": "celestial-mechanics",
        }
        return ctx


register_engine(ReboundEngine())
