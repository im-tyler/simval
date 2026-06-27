from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass
class RunContext:
    """Everything a set of checks needs to know about a run.

    Engine adapters populate this. MD-oriented fields are first-class; a future
    non-MD domain (fluids, N-body) populates `extra` with its own observables
    and ships domain-specific checks that read from `extra`."""
    run_dir: Path
    engine: str
    selection: str
    positions: np.ndarray | None = None
    reference: np.ndarray | None = None
    atom_names: list[str] | None = None
    ca_positions: np.ndarray | None = None
    ca_reference: np.ndarray | None = None
    ca_labels: list[str] | None = None
    energy: np.ndarray | None = None
    structure_path: Path | None = None
    tpr_path: Path | None = None
    trajectory_path: Path | None = None
    system_atom_types: list[str] | None = None
    ff_param_types: list[str] | None = None
    params: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    run_params: dict[str, Any] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def _find(run: Path, *patterns: str):
    from simval._util import find_files
    return find_files(run, *patterns)


class EngineAdapter:
    """Port for domain/engine expansion. A new physics domain implements this:
    `detect` recognizes its run-dirs; `load_context` reads its outputs into a
    RunContext that checks then operate on."""
    name = "base"

    def detect(self, run: Path) -> bool:
        raise NotImplementedError

    def load_context(self, run: Path, selection: str) -> RunContext:
        raise NotImplementedError


class SyntheticEngine(EngineAdapter):
    name = "synthetic"

    def detect(self, run: Path) -> bool:
        return bool(_find(run, "*.npy")) and not _find(run, "*.xtc")

    def load_context(self, run: Path, selection: str) -> RunContext:
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)

        e = _find(run, "energy.npy")
        if e is not None:
            ctx.energy = np.load(e)
            ctx.run_params["n_energy_samples"] = int(ctx.energy.size)

        pos = _find(run, "positions.npy")
        ref = _find(run, "reference.npy")
        if pos is not None and ref is not None:
            ctx.positions = np.load(pos)
            ctx.reference = np.load(ref)
            ctx.run_params["n_frames"] = int(ctx.positions.shape[0])
            ctx.run_params["n_atoms"] = int(ctx.positions.shape[1])

        sys_atoms_p = run / "atom_types.txt"
        ff_p = run / "ff_atom_types.txt"
        if sys_atoms_p.exists() and ff_p.exists():
            ctx.system_atom_types = [line.strip() for line in sys_atoms_p.read_text().splitlines() if line.strip()]
            ctx.ff_param_types = [line.strip() for line in ff_p.read_text().splitlines() if line.strip()]
            ctx.run_params["n_system_atom_types"] = len(set(ctx.system_atom_types))

        params_path = run / "params.json"
        if params_path.exists():
            from simval.units import Quantity
            raw = json.loads(params_path.read_text())
            ctx.params = {k: Quantity(v["value"], v["unit"]) for k, v in raw.items()}
        return ctx


class GromacsEngine(EngineAdapter):
    name = "gromacs"

    def detect(self, run: Path) -> bool:
        return bool(_find(run, "*.xtc", "*.dcd", "*.trr", "*.nc"))

    def load_context(self, run: Path, selection: str) -> RunContext:
        from simval import io, metadata as meta_mod
        from simval.units import Quantity

        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        ctx.run_params["engine"] = "gromacs"
        ctx.run_params["selection"] = selection

        top = _find(run, "*.gro", "*.pdb", "*.prmtop", "*.psf", "*.tpr")
        xtc = _find(run, "*.xtc", "*.dcd", "*.trr", "*.nc")
        ctx.trajectory_path = xtc
        if top and xtc:
            ctx.positions, ctx.reference, ctx.atom_names = io.load_trajectory(xtc, top, selection=selection)
            ctx.run_params["n_frames"] = int(ctx.positions.shape[0])
            ctx.run_params["n_selected_atoms"] = int(ctx.positions.shape[1])
            try:
                ctx.ca_positions, ctx.ca_reference, _ = io.load_trajectory(
                    xtc, top, selection="protein and name CA")
                ctx.ca_labels = io.load_residue_labels(top)
            except Exception:
                pass

        ctx.tpr_path = _find(run, "*.tpr")
        if ctx.tpr_path is not None:
            ctx.system_atom_types = io.load_atom_types(ctx.tpr_path, selection=selection) or None
            if ctx.system_atom_types:
                ctx.run_params["n_system_atom_types"] = len(set(ctx.system_atom_types))

        ff_p = run / "ff_atom_types.txt"
        if ff_p.exists():
            ctx.ff_param_types = [line.strip() for line in ff_p.read_text().splitlines() if line.strip()]

        ctx.structure_path = _find(run, "*.gro", "*.pdb")

        xvg = _find(run, "*.xvg")
        if xvg is not None:
            term, arr = io.load_preferred_energy(xvg)
            ctx.energy = arr
            ctx.run_params["energy_term"] = term
            ctx.run_params["n_energy_samples"] = int(ctx.energy.size)

        params_path = run / "params.json"
        if params_path.exists():
            raw = json.loads(params_path.read_text())
            ctx.params = {k: Quantity(v["value"], v["unit"]) for k, v in raw.items()}
            ctx.run_params["params"] = raw

        mdp = _find(run, "mdout.mdp", "*.mdp")
        top_top = _find(run, "*.top")
        methods_file = run / "methods.json"
        if methods_file.exists():
            md = __import__("json").loads(methods_file.read_text())
            ctx.metadata = md
            ctx.run_params["force_field"] = md.get("force_field")
            ctx.run_params["water_model"] = md.get("water")
        else:
            meta = meta_mod.build_metadata(mdp, top_top, gmx_version=_gmx_version())
            ctx.metadata = meta
            ctx.run_params["force_field"] = meta["force_field"]
            ctx.run_params["water_model"] = meta["water_model"]
            ctx.metadata["methods"] = meta_mod.render_methods(meta)
        return ctx


def _gmx_version() -> str | None:
    import subprocess
    try:
        out = subprocess.run(["gmx", "--version"], capture_output=True, text=True, timeout=10)
        for ln in out.stdout.splitlines():
            if ln.strip().startswith("GROMACS version:"):
                return ln.split(":", 1)[1].strip()
    except Exception:
        return None
    return None


_ENGINES: list[EngineAdapter] = [GromacsEngine(), SyntheticEngine()]
_optional_engines_loaded = False


def _load_optional_engines() -> None:
    global _optional_engines_loaded
    if _optional_engines_loaded:
        return
    _optional_engines_loaded = True
    try:
        import simval.nbody  # noqa: F401  (registers ReboundEngine if rebound installed)
    except Exception:
        pass
    try:
        import simval.wave  # noqa: F401  (registers WaveEngine; numpy-only)
    except Exception:
        pass
    try:
        import simval.fluid  # noqa: F401  (registers FluidEngine; numpy-only)
    except Exception:
        pass
    try:
        import simval.em  # noqa: F401  (registers EMEngine; numpy-only)
    except Exception:
        pass
    try:
        import simval.quantum  # noqa: F401  (registers QuantumEngine; numpy-only)
    except Exception:
        pass


def register_engine(adapter: EngineAdapter) -> None:
    _ENGINES.append(adapter)


def select_engine(run: Path) -> EngineAdapter:
    _load_optional_engines()
    for eng in _ENGINES:
        if eng.detect(run):
            return eng
    raise ValueError(f"no engine recognized run-dir: {run}")
