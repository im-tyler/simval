from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from simval import __version__
from simval.diagnostics import energy, equilibration, ff_coverage, params as params_mod
from simval.diagnostics import rmsd as rmsd_mod
from simval.manifest import build_manifest, write_manifest
from simval.units import Quantity


def _load_npy(run: Path, name: str):
    p = run / f"{name}.npy"
    return np.load(p) if p.exists() else None


def _find(run: Path, *patterns: str):
    for pat in patterns:
        hit = next(run.glob(pat), None)
        if hit:
            return hit
    return None


def diagnose(run_dir, *, out: str = "provenance.json", selection: str = "protein") -> dict:
    run = Path(run_dir)
    if _find(run, "*.xtc"):
        return _diagnose_gromacs(run, out=out, selection=selection)
    return _diagnose_synthetic(run, out=out)


def _diagnose_synthetic(run: Path, *, out: str) -> dict:
    results = []
    run_params: dict = {"engine": "synthetic"}

    energy_series = _load_npy(run, "energy")
    if energy_series is not None:
        results.append(energy.check_energy_drift(energy_series))
        run_params["n_energy_samples"] = int(energy_series.size)

    positions = _load_npy(run, "positions")
    reference = _load_npy(run, "reference")
    if positions is not None and reference is not None:
        results.append(rmsd_mod.check_rmsd_plateau(positions, reference))
        run_params["n_frames"] = int(positions.shape[0])
        run_params["n_atoms"] = int(positions.shape[1])
        results.append(equilibration.check_equilibration(rmsd_mod.rmsd_over_time(positions, reference)))

    atom_types_path = run / "atom_types.txt"
    ff_path = run / "ff_atom_types.txt"
    if atom_types_path.exists() and ff_path.exists():
        sys_atoms = [l.strip() for l in atom_types_path.read_text().splitlines() if l.strip()]
        ff_atoms = [l.strip() for l in ff_path.read_text().splitlines() if l.strip()]
        results.append(ff_coverage.check_ff_coverage(sys_atoms, ff_atoms))
        run_params["n_system_atom_types"] = len(set(sys_atoms))

    params_path = run / "params.json"
    if params_path.exists():
        raw = json.loads(params_path.read_text())
        qparams = {k: Quantity(v["value"], v["unit"]) for k, v in raw.items()}
        results.append(params_mod.check_params(qparams))
        run_params["params"] = raw

    artifact_files = [run / "energy.npy", run / "positions.npy", run / "reference.npy", run / "params.json"]
    files = [str(f) for f in artifact_files if Path(f).exists()]
    manifest = build_manifest(run_params, results, files=files, image_digest=None)
    write_manifest(manifest, run / out)
    return manifest


def _diagnose_gromacs(run: Path, *, out: str, selection: str) -> dict:
    from simval import io

    results = []
    run_params: dict = {"engine": "gromacs", "selection": selection}

    top = _find(run, "*.gro", "*.pdb", "*.tpr")
    xtc = _find(run, "*.xtc")
    if top and xtc:
        positions, reference, _names = io.load_trajectory(xtc, top, selection=selection)
        rseries = rmsd_mod.rmsd_over_time(positions, reference)
        results.append(rmsd_mod.check_rmsd_plateau(positions, reference))
        results.append(equilibration.check_equilibration(rseries))
        run_params["n_frames"] = int(positions.shape[0])
        run_params["n_selected_atoms"] = int(positions.shape[1])
        run_params["mean_rmsd_nm"] = float(rseries[1:].mean()) if rseries.size > 1 else 0.0

    tpr = _find(run, "*.tpr")
    if tpr:
        types = io.load_atom_types(tpr, selection=selection)
        ff_path = run / "ff_atom_types.txt"
        if types and ff_path.exists():
            ff_atoms = [l.strip() for l in ff_path.read_text().splitlines() if l.strip()]
            results.append(ff_coverage.check_ff_coverage(types, ff_atoms))
            run_params["n_system_atom_types"] = len(set(types))

    xvg = _find(run, "*.xvg")
    if xvg:
        e = io.load_energy_xvg(xvg)
        results.append(energy.check_energy_drift(e))
        run_params["n_energy_samples"] = int(e.size)

    params_path = run / "params.json"
    if params_path.exists():
        raw = json.loads(params_path.read_text())
        qparams = {k: Quantity(v["value"], v["unit"]) for k, v in raw.items()}
        results.append(params_mod.check_params(qparams))
        run_params["params"] = raw

    artifact_files = [f for f in (xtc, top, xvg) if f]
    files = [str(f) for f in artifact_files]
    manifest = build_manifest(run_params, results, files=files, image_digest=None)
    write_manifest(manifest, run / out)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="simval", description="Deterministic MD verification")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnose", help="run diagnostics on a run directory; writes provenance.json")
    d.add_argument("run_dir")
    d.add_argument("--out", default="provenance.json")
    d.add_argument("--selection", default="protein", help="MDAnalysis selection (default: protein)")
    args = parser.parse_args(argv)

    if args.cmd == "diagnose":
        manifest = diagnose(args.run_dir, out=args.out, selection=args.selection)
        verdict = manifest["verdict"]
        print(f"simval {__version__} | verdict: {verdict.upper()} | {len(manifest['diagnostics'])} checks")
        for r in manifest["diagnostics"]:
            flag = "PASS" if r["passed"] else "FAIL"
            print(f"  [{flag}] {r['name']:<16} value={r['value']:.4g} threshold={r['threshold']:.4g}")
        return 0 if verdict == "pass" else 1
    return 0
