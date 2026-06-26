from __future__ import annotations

from pathlib import Path

import numpy as np

from simval.diagnostics import rmsd as rmsd_mod
from simval.oracle.cases import ReferenceCase
from simval.result import DiagnosticResult


def compute_metrics(run_dir, *, selection: str = "protein and name CA") -> dict:
    """Scalar metrics for a candidate run, computed the same way as references.
    Dispatches by engine so the oracle is domain-general (MD today, N-body too)."""
    from simval.context import select_engine

    run = Path(run_dir)
    engine = select_engine(run)
    if engine.name == "nbody-rebound":
        return _nbody_metrics(run)
    if engine.name == "wave-fdtd":
        return _wave_metrics(run)
    return _md_metrics(run, selection)


def _md_metrics(run: Path, selection: str) -> dict:
    from simval import io

    top = _find(run, "*.gro", "*.pdb", "*.tpr")
    xtc = _find(run, "*.xtc")
    if not (top and xtc):
        raise FileNotFoundError(f"run-dir {run} needs a trajectory (.xtc) and topology (.gro/.pdb/.tpr)")

    positions, reference, _names = io.load_trajectory(xtc, top, selection=selection)
    rseries = rmsd_mod.rmsd_over_time(positions, reference)

    com = positions.mean(axis=1, keepdims=True)
    rg_per_frame = np.sqrt(((positions - com) ** 2).sum(axis=2).mean(axis=1))

    plateau = rmsd_mod.check_rmsd_plateau(positions, reference)

    metrics = {
        "n_frames": int(positions.shape[0]),
        "n_selected_atoms": int(positions.shape[1]),
        "mean_rmsd_nm": float(rseries[1:].mean()) if rseries.size > 1 else 0.0,
        "final_rmsd_nm": float(rseries[-1]),
        "rmsd_tail_drift_fraction": float(plateau.value),
        "mean_rg_nm": float(rg_per_frame.mean()),
        "final_rg_nm": float(rg_per_frame[-1]),
    }

    xvg = _find(run, "*.xvg")
    if xvg:
        from simval.diagnostics import energy as energy_mod
        _term, e = io.load_preferred_energy(xvg)
        metrics["energy_relative_range"] = float(energy_mod.check_energy_drift(e).value)

    return metrics


def _nbody_metrics(run: Path) -> dict:
    from simval import nbody as nbody_mod

    data = nbody_mod.integrate_system(run / "system.json", samples=120)
    e = data["energy"]
    L = data["L_magnitude"]
    com = data["com"]
    e_rel = float((e.max() - e.min()) / (abs(e.mean()) + 1e-15))
    L_rel = float((L.max() - L.min()) / (abs(L.mean()) + 1e-15))
    com_drift = float(np.sqrt(((com - com[0]) ** 2).sum(axis=1)).max())
    return {
        "n_samples": int(e.size),
        "energy_relative_range": e_rel,
        "angular_momentum_relative_range": L_rel,
        "com_drift_max": com_drift,
    }


def _wave_metrics(run: Path) -> dict:
    import json

    from simval.wave import check_wave_energy, integrate_wave

    cfg = json.loads((run / "wave.json").read_text())
    data = integrate_wave(cfg)
    growth = check_wave_energy(data["energy"], src_on_index=data["src_on"] // 4)
    return {
        "cfl": float(data["cfl"]),
        "energy_growth": float(growth.value),
        "n_steps": int(data["n_steps"]),
    }


_DEFAULT_TOLERANCES = {
    "n_selected_atoms": ("exact",),
    "mean_rmsd_nm": ("rel", 0.10),
    "final_rmsd_nm": ("rel", 0.10),
    "rmsd_tail_drift_fraction": ("rel", 0.25),
    "mean_rg_nm": ("rel", 0.02),
    "final_rg_nm": ("rel", 0.03),
    "energy_relative_range": ("rel", 0.25),
}


def _within(kind, candidate, reference, tol):
    if kind == "exact":
        return candidate == reference
    if kind == "rel":
        denom = abs(reference) + 1e-12
        return abs(candidate - reference) / denom <= tol
    if kind == "abs":
        return abs(candidate - reference) <= tol
    raise ValueError(f"unknown tolerance kind: {kind}")


def compare_metrics(candidate: dict, reference: dict, tolerances: dict | None = None) -> dict:
    """Pure comparison. Returns {metric: {ref, candidate, delta, passed}} + overall 'passed'."""
    tols = dict(_DEFAULT_TOLERANCES)
    if tolerances:
        tols.update(tolerances)
    out: dict = {}
    all_pass = True
    for metric, ref_val in reference.items():
        if metric not in candidate or metric not in tols:
            continue
        kind = tols[metric][0]
        cand_val = candidate[metric]
        passed = _within(kind, cand_val, ref_val, tols[metric][1] if len(tols[metric]) > 1 else None)
        denom = abs(ref_val) + 1e-12
        out[metric] = {
            "reference": ref_val,
            "candidate": cand_val,
            "delta_rel": float(abs(cand_val - ref_val) / denom) if kind != "exact" else (0.0 if passed else 1.0),
            "tol_kind": kind,
            "tol": tols[metric][1] if len(tols[metric]) > 1 else None,
            "passed": bool(passed),
        }
        all_pass = all_pass and passed
    out["__passed__"] = bool(all_pass)
    return out


def validate(run_dir, case: ReferenceCase | str, *, selection: str | None = None) -> DiagnosticResult:
    if isinstance(case, str):
        from simval.oracle.cases import get_case
        case = get_case(case)
    sel = selection or case.selection
    candidate = compute_metrics(run_dir, selection=sel)
    compared = compare_metrics(candidate, case.reference_metrics, case.tolerances)
    passed = compared.pop("__passed__")
    n_checked = len(compared)
    n_failed = sum(1 for v in compared.values() if not v["passed"])
    detail = {
        "case": case.name,
        "selection": sel,
        "n_checked": n_checked,
        "n_failed": n_failed,
        "metrics": compared,
        "candidate_metrics": candidate,
    }
    return DiagnosticResult(
        name="reference_oracle",
        passed=passed,
        threshold=0.0,
        value=float(n_failed),
        detail=detail,
    )


def _find(run: Path, *patterns: str):
    from simval._util import find_files
    return find_files(run, *patterns)
