"""Ontos engine adapter: run-dir detection + context wiring.

The reference implementation and stream verifier live in simval.ontos
(stdlib-only); this module holds the EngineAdapter plumbing so the
verifier stays importable without numpy.
"""
from __future__ import annotations

import json
from pathlib import Path

from simval.context import EngineAdapter, RunContext, register_engine
from simval.ontos import verify_stream


class OntosEngine(EngineAdapter):
    name = "ontos"

    def detect(self, run: Path) -> bool:
        return (run / "ontos.stream").exists() and (run / "ontos.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        meta = json.loads((run / "ontos.json").read_text())
        if "seed" not in meta:
            raise ValueError("ontos.json must contain an integer 'seed'")
        summary = verify_stream(run / "ontos.stream", int(meta["seed"]))
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.extra = {"ontos_summary": summary}
        ctx.run_params = {
            "engine": self.name,
            "seed": int(meta["seed"]),
            "domain": "discrete-multiscale",
            "ticks": summary["ticks_verified"],
        }
        return ctx


register_engine(OntosEngine())
