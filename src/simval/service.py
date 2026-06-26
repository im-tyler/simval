"""Stable service API. Any UI (web, notebook, agent) or future expansion calls
these — never the CLI or pipeline internals directly. This is the contract that
stays stable while engines/checks/oracle cases grow behind it."""
from __future__ import annotations

from pathlib import Path

from simval.context import _ENGINES, select_engine
from simval.oracle import list_cases
from simval.pipeline import diagnose


def list_engines() -> list[str]:
    return [e.name for e in _ENGINES]


def engine_for(run_dir) -> str:
    return select_engine(Path(run_dir)).name


def inspect(run_dir, *, selection: str = "protein") -> dict:
    """Load a run without running checks — returns the context snapshot.
    Useful for a UI to show what would be analyzed before running."""
    run = Path(run_dir)
    engine = select_engine(run)
    ctx = engine.load_context(run, selection)
    return {
        "engine": engine.name,
        "selection": selection,
        "run_params": ctx.run_params,
        "metadata": ctx.metadata,
        "skipped": ctx.skipped,
        "has": {
            "trajectory": ctx.positions is not None,
            "energy": ctx.energy is not None,
            "structure": ctx.structure_path is not None,
            "tpr": ctx.tpr_path is not None,
            "params": ctx.params is not None,
        },
    }


def diagnose_run(run_dir, *, selection: str = "protein", out: str = "provenance.json") -> dict:
    return diagnose(run_dir, out=out, selection=selection)


def validate_run(run_dir, case: str, *, selection: str | None = None) -> dict:
    from simval.oracle import validate as oracle_validate
    return oracle_validate(run_dir, case, selection=selection).to_dict()


def cases() -> list[str]:
    return list_cases()


def compare_runs(run_a, run_b, *, selection: str = "protein and name CA") -> dict:
    from simval.compare import compare_runs as _cmp
    return _cmp(run_a, run_b, selection=selection)


__all__ = [
    "list_engines", "engine_for", "inspect",
    "diagnose_run", "validate_run", "cases", "compare_runs",
]
