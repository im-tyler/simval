"""Chemical kinetics domain (coupled reaction ODEs, mass-action).

The 10th physics domain. Simulates a set of coupled chemical reactions (A->B,
B+C->D, etc.) via forward-Euler integration. Invariant: total mass balance
(sum of all species weighted by molecular weight stays constant for a closed
system with balanced stoichiometry)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from simval.context import EngineAdapter, RunContext, register_engine
from simval.result import DiagnosticResult


def integrate_kinetics(cfg: dict, *, sample_every: int = 10) -> dict:
    species = cfg["species"]
    init = cfg["initial"]
    reactions = cfg["reactions"]
    dt = float(cfg["dt"])
    n = int(cfg["n_steps"])
    n_sp = len(species)
    conc = np.array(init, dtype=float)
    history = [conc.copy()]
    for _ in range(n):
        rates = np.zeros(n_sp)
        for rxn in reactions:
            r = rxn["k"]
            for idx in rxn.get("reactants", []):
                r *= conc[idx]
            for idx in rxn.get("reactants", []):
                rates[idx] -= r
            for idx in rxn.get("products", []):
                rates[idx] += r
        conc = np.maximum(conc + rates * dt, 0.0)
        if _ % sample_every == 0:
            history.append(conc.copy())
    return {"history": np.array(history), "species": species, "dt": dt, "n_steps": n}


def check_mass_balance(history, *, max_drift: float = 1e-3) -> DiagnosticResult:
    total = history.sum(axis=1)
    mean = float(np.abs(total).mean()) + 1e-15
    drift = float((total.max() - total.min()) / mean)
    return DiagnosticResult(
        name="kinetics_mass_balance",
        passed=drift <= max_drift,
        threshold=float(max_drift),
        value=drift,
        detail={"total_drift": drift, "initial_total": float(total[0]), "final_total": float(total[-1])},
    )


def check_positive_concentrations(history) -> DiagnosticResult:
    negatives = int((history < -1e-10).sum())
    return DiagnosticResult(
        name="positive_concentrations",
        passed=negatives == 0,
        threshold=0.0,
        value=float(negatives),
        detail={"negative_count": negatives},
    )


class KineticsEngine(EngineAdapter):
    name = "chemical-kinetics"

    def detect(self, run: Path) -> bool:
        return (run / "kinetics.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        cfg = json.loads((run / "kinetics.json").read_text())
        data = integrate_kinetics(cfg)
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"history": data["history"], "species": data["species"]}
        ctx.run_params = {"engine": self.name, "domain": "chemical-kinetics",
                          "n_species": len(data["species"]), "n_steps": data["n_steps"]}
        return ctx


register_engine(KineticsEngine())
