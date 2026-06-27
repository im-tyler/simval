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
from simval import fluid  # noqa: F401  (registers FluidEngine + exposes fluid checks)
from simval import em  # noqa: F401  (registers EMEngine + exposes EM checks)
from simval import quantum  # noqa: F401  (registers QuantumEngine + exposes quantum checks)
from simval import fep  # noqa: F401  (registers FepEngine + exposes FEP checks)
from simval import pyscf_eng  # noqa: F401  (registers PyscfEngine + exposes SCF checks)
from simval import qiskit_eng  # noqa: F401  (registers QiskitEngine + exposes circuit checks)
from simval import kinetics  # noqa: F401
from simval import diffusion  # noqa: F401
from simval import relativistic  # noqa: F401
from simval.manifest import build_manifest, write_manifest


def run_checks(ctx: RunContext, thresholds: dict | None = None) -> list:
    """Run every check whose inputs are present on the context.
    Adding a check = adding a branch here; adding a domain = an engine that
    populates the context with that domain's observables."""
    from simval import thresholds as T
    t = T.load(ctx.run_dir, thresholds)

    results = []

    if ctx.energy is not None:
        results.append(energy.check_energy_drift(ctx.energy, **T.kwargs_for("energy_drift", t)))

    if ctx.positions is not None and ctx.reference is not None:
        rseries = rmsd_mod.rmsd_over_time(ctx.positions, ctx.reference)
        results.append(rmsd_mod.check_rmsd_plateau(ctx.positions, ctx.reference, **T.kwargs_for("rmsd_plateau", t)))
        results.append(equilibration.check_equilibration(rseries, **T.kwargs_for("structural_equilibration", t)))

    if ctx.ca_positions is not None and ctx.ca_reference is not None:
        results.append(rmsf_mod.check_rmsf(
            ctx.ca_positions, ctx.ca_reference, labels=ctx.ca_labels,
            **T.kwargs_for("per_residue_rmsf", t)))

    if ctx.system_atom_types is not None and ctx.ff_param_types is not None:
        results.append(ff_coverage.check_ff_coverage(ctx.system_atom_types, ctx.ff_param_types))

    if ctx.structure_path is not None:
        results.append(prep_mod.check_box_cutoff(ctx.structure_path, rcoulomb=1.0, **T.kwargs_for("box_cutoff", t)))
        results.append(prep_mod.check_steric_clashes(ctx.structure_path))
        if ctx.tpr_path is not None:
            try:
                results.append(prep_mod.check_charge_state(ctx.structure_path, tpr_path=ctx.tpr_path, **T.kwargs_for("charge_state", t)))
            except Exception as e:
                ctx.skipped["charge_state"] = str(e)[:160]
        if ctx.trajectory_path is not None:
            try:
                results.append(hbonds.check_hydrogen_bonds(ctx.structure_path, ctx.trajectory_path, **T.kwargs_for("hydrogen_bonds", t)))
            except Exception as e:
                ctx.skipped["hydrogen_bonds"] = str(e)[:160]

    if ctx.params is not None:
        results.append(params_mod.check_params(ctx.params))

    if "L_magnitude" in ctx.extra:
        results.append(nbody.check_angular_momentum(ctx.extra["L_magnitude"], **T.kwargs_for("angular_momentum", t)))
    if "com" in ctx.extra:
        results.append(nbody.check_com_drift(ctx.extra["com"], **T.kwargs_for("com_drift", t)))

    if "cfl" in ctx.extra:
        results.append(wave.check_cfl(ctx.extra["cfl"], **T.kwargs_for("cfl_stability", t)))
        results.append(wave.check_wave_energy(
            ctx.extra["wave_energy"], src_on_index=ctx.extra.get("src_on_index", 0),
            **T.kwargs_for("wave_energy_bounded", t)))

    if "tau" in ctx.extra and "mass" in ctx.extra:
        results.append(fluid.check_tau_stability(ctx.extra["tau"]))
        results.append(fluid.check_mass_conservation(ctx.extra["mass"]))

    if "courant" in ctx.extra and "em_energy" in ctx.extra:
        results.append(em.check_courant(ctx.extra["courant"]))
        results.append(em.check_em_energy(
            ctx.extra["em_energy"], src_on_index=ctx.extra.get("src_on_index", 0)))

    if "norm" in ctx.extra and "p_up" in ctx.extra:
        results.append(quantum.check_norm_conservation(ctx.extra["norm"]))
        results.append(quantum.check_rabi_oscillates(ctx.extra["p_up"]))

    if "u_nk" in ctx.extra:
        results.append(fep.check_free_energy(ctx.extra["u_nk"]))
        results.append(fep.check_overlap(ctx.extra["u_nk"]))
        results.append(fep.check_hysteresis(ctx.extra["u_nk"], ctx.extra.get("u_nk_reverse")))

    if "scf_energies" in ctx.extra:
        results.append(pyscf_eng.check_scf_convergence(ctx.extra["scf_energies"]))
        results.append(pyscf_eng.check_energy_sane(
            ctx.extra["final_energy"], ctx.extra["n_electrons"]))

    if "statevector" in ctx.extra:
        results.append(qiskit_eng.check_norm_conservation(ctx.extra["statevector"]))
        results.append(qiskit_eng.check_measurement_distribution(
            ctx.extra["probabilities"], ctx.extra.get("expected_probabilities")))

    if "history" in ctx.extra and "species" in ctx.extra:
        results.append(kinetics.check_mass_balance(ctx.extra["history"]))
        results.append(kinetics.check_positive_concentrations(ctx.extra["history"]))

    if "fourier" in ctx.extra:
        results.append(diffusion.check_fourier_stability(ctx.extra["fourier"]))
        results.append(diffusion.check_heat_conservation(ctx.extra["heat_energy"]))

    if "gamma" in ctx.extra:
        results.append(relativistic.check_relativistic_energy(ctx.extra["gamma"]))

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


def diagnose(run_dir, *, out: str = "provenance.json", selection: str = "protein",
             thresholds: dict | None = None) -> dict:
    run = Path(run_dir)
    engine = select_engine(run)
    ctx = engine.load_context(run, selection)
    results = run_checks(ctx, thresholds=thresholds)

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
