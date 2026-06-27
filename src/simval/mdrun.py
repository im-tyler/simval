"""Run MD simulations via OpenMM, then auto-verify.

Closes the loop: simval can now PRODUCE a simulation (via OpenMM) AND verify it
in one command. The user provides a PDB (or a PDB ID to fetch); simval runs the
simulation, writes the trajectory, and diagnoses the output."""
from __future__ import annotations

import json
from pathlib import Path


def run_md(
    pdb_path,
    out_dir,
    *,
    steps: int = 5000,
    dt: float = 0.002,
    temp: float = 300,
    padding: float = 1.0,
    report_every: int = 100,
) -> Path:
    """Run a short MD simulation via OpenMM -> topology.pdb + traj.dcd + energy.xvg.
    Returns the output directory (a simval run-dir ready for diagnose)."""
    from openmm import LangevinMiddleIntegrator, Platform, unit
    from openmm.app import (
        DCDReporter,
        ForceField,
        HBonds,
        Modeller,
        PME,
        PDBFile,
        Simulation,
    )
    from pdbfixer import PDBFixer

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixer = PDBFixer(filename=str(pdb_path))
    fixer.findMissingResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.0)

    ff = ForceField("amber14-all.xml", "amber14/tip3pfb.xml")
    modeller = Modeller(fixer.topology, fixer.positions)
    modeller.deleteWater()
    modeller.addSolvent(ff, model="tip3p", padding=padding * unit.nanometer)

    system = ff.createSystem(
        modeller.topology, nonbondedMethod=PME,
        nonbondedCutoff=1.0 * unit.nanometer, constraints=HBonds,
    )
    integrator = LangevinMiddleIntegrator(
        temp * unit.kelvin, 1.0 / unit.picosecond, dt * unit.picoseconds,
    )
    sim = Simulation(modeller.topology, system, integrator, Platform.getPlatformByName("CPU"))
    sim.context.setPositions(modeller.positions)
    sim.minimizeEnergy(maxIterations=100)
    sim.context.setVelocitiesToTemperature(temp * unit.kelvin)

    energy_log = open(out / "energy.xvg", "w")
    energy_log.write('@ s0 legend "Potential"\n')

    def report(_s):
        st = _s.context.getState(getEnergy=True)
        t = st.getTime().value_in_unit(unit.picosecond)
        e = st.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole)
        energy_log.write(f"{t:.4f} {e:.4f}\n")
        energy_log.flush()

    sim.reporters.append(DCDReporter(str(out / "traj.dcd"), report_every))
    for _ in range(0, steps, report_every):
        sim.step(report_every)
        report(sim)
    energy_log.close()

    PDBFile.writeFile(
        sim.topology,
        sim.context.getState(getPositions=True).getPositions(),
        open(out / "topology.pdb", "w"),
    )
    methods = {
        "force_field": "amber14", "water_model": "tip3p",
        "integrator": "LangevinMiddle", "dt_ps": dt,
        "temperature_K": temp, "n_steps": steps, "ensemble": "NVT",
        "methods": (
            f"MD was performed with OpenMM using the AMBER14 force field and TIP3P water. "
            f"Integration: LangevinMiddle, dt = {dt} ps. Nonbonded: PME (1.0 nm cutoff). "
            f"Ensemble: NVT, {temp} K. Production: {steps * dt:.1f} ps."
        ),
    }
    (out / "methods.json").write_text(json.dumps(methods, indent=2))
    return out
