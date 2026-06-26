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


def diagnose(run_dir, *, out: str = "provenance.json") -> dict:
    run = Path(run_dir)
    results = []
    run_params: dict = {}

    energy_series = _load_npy(run, "energy")
    if energy_series is not None:
        results.append(energy.check_energy_drift(energy_series))
        run_params["n_energy_samples"] = int(energy_series.size)

    positions = _load_npy(run, "positions")
    reference = _load_npy(run, "reference")
    rmsd_series = None
    if positions is not None and reference is not None:
        rmsd_series = rmsd_mod.rmsd_over_time(positions, reference)
        results.append(rmsd_mod.check_rmsd_plateau(positions, reference))
        run_params["n_frames"] = int(positions.shape[0])
        run_params["n_atoms"] = int(positions.shape[1])

    series_for_eq = rmsd_series if rmsd_series is not None else energy_series
    if series_for_eq is not None:
        results.append(equilibration.check_equilibration(series_for_eq))

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

    artifact_files = [
        run / "energy.npy",
        run / "positions.npy",
        run / "reference.npy",
        run / "params.json",
    ]
    files = [str(f) for f in artifact_files if Path(f).exists()]

    manifest = build_manifest(run_params, results, files=files, image_digest=None)
    write_manifest(manifest, run / out)
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="simval", description="Deterministic MD verification")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diagnose", help="run diagnostics on a run directory; writes provenance.json")
    d.add_argument("run_dir")
    d.add_argument("--out", default="provenance.json")
    args = parser.parse_args(argv)

    if args.cmd == "diagnose":
        manifest = diagnose(args.run_dir, out=args.out)
        verdict = manifest["verdict"]
        print(f"simval {__version__} | verdict: {verdict.upper()} | {len(manifest['diagnostics'])} checks")
        for r in manifest["diagnostics"]:
            flag = "PASS" if r["passed"] else "FAIL"
            print(f"  [{flag}] {r['name']:<16} value={r['value']:.4g} threshold={r['threshold']:.4g}")
        return 0 if verdict == "pass" else 1
    return 0
