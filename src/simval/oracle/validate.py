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
    if engine.name == "fluid-lbm":
        return _fluid_metrics(run)
    if engine.name == "em-fdtd":
        return _em_metrics(run)
    if engine.name == "quantum-spin":
        return _quantum_metrics(run)
    if engine.name == "fep":
        return _fep_metrics(run)
    if engine.name == "qc-pyscf":
        return _pyscf_metrics(run)
    if engine.name == "qc-qiskit":
        return _qiskit_metrics(run)
    if engine.name == "chemical-kinetics":
        return _kinetics_metrics(run)
    if engine.name == "heat-diffusion":
        return _diffusion_metrics(run)
    if engine.name == "relativistic-boris":
        return _relativistic_metrics(run)
    return _md_metrics(run, selection)


def _md_metrics(run: Path, selection: str) -> dict:
    from simval import io

    top = _find(run, "*.gro", "*.pdb", "*.prmtop", "*.psf", "*.tpr")
    xtc = _find(run, "*.xtc", "*.dcd", "*.trr", "*.nc")
    if not (top and xtc):
        raise FileNotFoundError(f"run-dir {run} needs a trajectory (.xtc/.dcd/.trr/.nc) and topology (.gro/.pdb/.prmtop/.psf/.tpr)")

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


def _fluid_metrics(run: Path) -> dict:
    import json

    from simval.fluid import check_mass_conservation, check_tau_stability, integrate_fluid

    cfg = json.loads((run / "fluid.json").read_text())
    data = integrate_fluid(cfg)
    tau = check_tau_stability(data["tau"])
    mass = check_mass_conservation(data["mass"])
    return {
        "tau": float(data["tau"]),
        "mass_drift": float(mass.value),
        "tau_in_range": 1.0 if tau.passed else 0.0,
    }


def _em_metrics(run: Path) -> dict:
    import json

    from simval.em import check_em_energy, integrate_em

    cfg = json.loads((run / "em.json").read_text())
    data = integrate_em(cfg)
    eg = check_em_energy(data["energy"], src_on_index=data["src_on"] // 10)
    return {
        "courant": float(data["courant"]),
        "em_energy_growth": float(eg.value),
        "n_steps": int(data["n_steps"]),
    }


def _quantum_metrics(run: Path) -> dict:
    import json

    from simval.quantum import check_norm_conservation, evolve_spin

    cfg = json.loads((run / "quantum.json").read_text())
    data = evolve_spin(cfg)
    nc = check_norm_conservation(data["norm"])
    return {
        "norm_drift": float(nc.value),
        "p_up_swing": float(data["p_up"].max() - data["p_up"].min()),
        "n_steps": int(data["n_steps"]),
    }


def _fep_metrics(run: Path) -> dict:
    from simval.fep import FepEngine, check_free_energy, check_overlap

    ctx = FepEngine().load_context(run, "n/a")
    u_nk = ctx.extra["u_nk"]
    fe = check_free_energy(u_nk)
    ov = check_overlap(u_nk)
    return {
        "deltaG": float(fe.value),
        "overlap_min_eig": float(ov.value),
    }


def _pyscf_metrics(run: Path) -> dict:
    from simval.pyscf_eng import PyscfEngine

    ctx = PyscfEngine().load_context(run, "n/a")
    return {
        "final_energy_hartree": float(ctx.extra["final_energy"]),
        "converged": 1.0 if ctx.extra["converged"] else 0.0,
        "n_electrons": int(ctx.extra["n_electrons"]),
    }


def _qiskit_metrics(run: Path) -> dict:
    from simval.qiskit_eng import QiskitEngine, check_norm_conservation

    ctx = QiskitEngine().load_context(run, "n/a")
    nm = check_norm_conservation(ctx.extra["statevector"])
    return {
        "norm_drift": float(nm.value),
        "n_qubits": int(ctx.extra["n_qubits"]),
    }


def _kinetics_metrics(run: Path) -> dict:
    import json

    from simval.kinetics import check_mass_balance, integrate_kinetics

    cfg = json.loads((run / "kinetics.json").read_text())
    data = integrate_kinetics(cfg)
    mb = check_mass_balance(data["history"])
    return {"mass_balance_drift": float(mb.value), "n_steps": int(data["n_steps"])}


def _diffusion_metrics(run: Path) -> dict:
    import json

    from simval.diffusion import check_heat_conservation, integrate_diffusion

    cfg = json.loads((run / "diffusion.json").read_text())
    data = integrate_diffusion(cfg)
    hc = check_heat_conservation(data["energy"])
    return {"fourier": float(data["fourier"]), "energy_drift": float(hc.value)}


def _relativistic_metrics(run: Path) -> dict:
    import json

    from simval.relativistic import check_relativistic_energy, integrate_relativistic

    cfg = json.loads((run / "relativistic.json").read_text())
    data = integrate_relativistic(cfg)
    re = check_relativistic_energy(data["gamma"])
    return {"gamma_drift": float(re.value), "n_steps": int(data["n_steps"])}


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
    run = Path(run_dir)
    from simval.context import select_engine
    run_engine = select_engine(run).name
    if case.engine and case.engine != run_engine:
        return DiagnosticResult(
            name="reference_oracle",
            passed=False,
            threshold=0.0,
            value=0.0,
            detail={
                "case": case.name,
                "run_engine": run_engine,
                "case_engine": case.engine,
                "error": f"domain mismatch: run is '{run_engine}', case is '{case.engine}'",
                "n_checked": 0, "n_failed": 0, "metrics": {}, "candidate_metrics": {},
            },
        )
    sel = selection or case.selection
    candidate = compute_metrics(run_dir, selection=sel)
    compared = compare_metrics(candidate, case.reference_metrics, case.tolerances)
    passed = compared.pop("__passed__")
    n_checked = len(compared)
    n_failed = sum(1 for v in compared.values() if not v["passed"])
    if n_checked == 0:
        passed = False
        compared["_domain_mismatch"] = {
            "reference_metrics": sorted(case.reference_metrics),
            "candidate_metrics": sorted(candidate),
            "note": "no overlapping metrics despite matching engine",
        }
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
