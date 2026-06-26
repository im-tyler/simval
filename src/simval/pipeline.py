from __future__ import annotations

from pathlib import Path

from simval.context import RunContext, select_engine
from simval.diagnostics import energy, equilibration, ff_coverage, hbonds
from simval.diagnostics import params as params_mod
from simval.diagnostics import prep as prep_mod
from simval.diagnostics import rmsd as rmsd_mod
from simval.diagnostics import rmsf as rmsf_mod
from simval import nbody  # noqa: F401  (registers ReboundEngine + exposes n-body checks)
from simval import wave  # noqa: F401  (registers WaveEngine + exposes wave checks)
from simval.manifest import build_manifest, write_manifest


def run_checks(ctx: RunContext) -> list:
    """Run every check whose inputs are present on the context.
    Adding a check = adding a branch here; adding a domain = an engine that
    populates the context with that domain's observables."""
    results = []

    if ctx.energy is not None:
        results.append(energy.check_energy_drift(ctx.energy))

    if ctx.positions is not None and ctx.reference is not None:
        rseries = rmsd_mod.rmsd_over_time(ctx.positions, ctx.reference)
        results.append(rmsd_mod.check_rmsd_plateau(ctx.positions, ctx.reference))
        results.append(equilibration.check_equilibration(rseries))

    if ctx.ca_positions is not None and ctx.ca_reference is not None:
        results.append(rmsf_mod.check_rmsf(
            ctx.ca_positions, ctx.ca_reference, labels=ctx.ca_labels))

    if ctx.system_atom_types is not None and ctx.ff_param_types is not None:
        results.append(ff_coverage.check_ff_coverage(ctx.system_atom_types, ctx.ff_param_types))

    if ctx.structure_path is not None:
        results.append(prep_mod.check_box_cutoff(ctx.structure_path, rcoulomb=1.0))
        results.append(prep_mod.check_steric_clashes(ctx.structure_path))
        if ctx.tpr_path is not None:
            try:
                results.append(prep_mod.check_charge_state(ctx.structure_path, tpr_path=ctx.tpr_path))
            except Exception as e:
                ctx.skipped["charge_state"] = str(e)[:160]
        if ctx.trajectory_path is not None:
            try:
                results.append(hbonds.check_hydrogen_bonds(ctx.structure_path, ctx.trajectory_path))
            except Exception as e:
                ctx.skipped["hydrogen_bonds"] = str(e)[:160]

    if ctx.params is not None:
        results.append(params_mod.check_params(ctx.params))

    if "L_magnitude" in ctx.extra:
        results.append(nbody.check_angular_momentum(ctx.extra["L_magnitude"]))
    if "com" in ctx.extra:
        results.append(nbody.check_com_drift(ctx.extra["com"]))

    if "cfl" in ctx.extra:
        results.append(wave.check_cfl(ctx.extra["cfl"]))
        results.append(wave.check_wave_energy(
            ctx.extra["wave_energy"], src_on_index=ctx.extra.get("src_on_index", 0)))

    return results


def _artifact_files(ctx: RunContext) -> list[str]:
    run = ctx.run_dir
    out = []
    for pat in ("*.xtc", "*.gro", "*.pdb", "*.tpr", "*.xvg", "*.mdp",
                "mdout.mdp", "*.top", "*.npy", "params.json"):
        hit = next(run.glob(pat), None)
        if hit:
            out.append(str(hit))
    return out


def diagnose(run_dir, *, out: str = "provenance.json", selection: str = "protein") -> dict:
    run = Path(run_dir)
    engine = select_engine(run)
    ctx = engine.load_context(run, selection)
    results = run_checks(ctx)

    run_params = dict(ctx.run_params)
    run_params["engine"] = engine.name
    if ctx.skipped:
        run_params["skipped"] = ctx.skipped

    manifest = build_manifest(run_params, results, files=_artifact_files(ctx), image_digest=None)
    if ctx.metadata:
        manifest["metadata"] = ctx.metadata
        if "methods" in ctx.metadata:
            manifest["methods"] = ctx.metadata["methods"]
    write_manifest(manifest, run / out)
    return manifest
