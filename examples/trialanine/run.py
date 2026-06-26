"""Run a short OpenMM equilibration on an input PDB (default: the GROMACS
lysozyme 1AKI) -> topology.pdb + traj.dcd + energy.xvg, readable by simval's
generalized MD adapter. Proves a second MD engine through the same port.
Usage: python run.py <input.pdb> <out_dir>"""
import sys
from pathlib import Path

from openmm import LangevinMiddleIntegrator, Platform, unit
from openmm.app import (
    DCDReporter,
    ForceField,
    HBonds,
    Modeller,
    PME,
    PDBFile,
    Simulation,
    StateDataReporter,
)
from pdbfixer import PDBFixer


def run(pdb_path: str, out_dir: str):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    fixer = PDBFixer(filename=pdb_path)
    fixer.findMissingResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.0)

    ff = ForceField("amber14-all.xml", "amber14/tip3pfb.xml")
    modeller = Modeller(fixer.topology, fixer.positions)
    modeller.deleteWater()
    modeller.addSolvent(ff, model="tip3p", padding=1.0 * unit.nanometer)

    system = ff.createSystem(
        modeller.topology, nonbondedMethod=PME,
        nonbondedCutoff=1.0 * unit.nanometer, constraints=HBonds,
    )
    integrator = LangevinMiddleIntegrator(
        300 * unit.kelvin, 1.0 / unit.picosecond, 0.002 * unit.picoseconds,
    )
    sim = Simulation(modeller.topology, system, integrator, Platform.getPlatformByName("CPU"))
    sim.context.setPositions(modeller.positions)
    sim.minimizeEnergy(maxIterations=100)
    sim.context.setVelocitiesToTemperature(300 * unit.kelvin)

    n_steps, report_every = 5000, 100  # 10 ps, 50 frames
    energy_log = open(out / "energy.xvg", "w")
    energy_log.write('@ s0 legend "Potential"\n')

    def report(_s):
        st = _s.context.getState(getEnergy=True)
        t = st.getTime().value_in_unit(unit.picosecond)
        e = st.getPotentialEnergy().value_in_unit(unit.kilojoule_per_mole)
        energy_log.write(f"{t:.4f} {e:.4f}\n")
        energy_log.flush()

    sim.reporters.append(DCDReporter(str(out / "traj.dcd"), report_every))
    sim.reporters.append(StateDataReporter(str(out / "openmm.log"), report_every, step=True, time=True))
    for _ in range(0, n_steps, report_every):
        sim.step(report_every)
        report(sim)
    energy_log.close()

    PDBFile.writeFile(
        sim.topology,
        sim.context.getState(getPositions=True).getPositions(),
        open(out / "topology.pdb", "w"),
    )
    import json
    methods = {
        "force_field": "amber14", "water_model": "tip3p",
        "integrator": "LangevinMiddle", "dt_ps": 0.002,
        "temperature_K": 300, "n_steps": n_steps, "ensemble": "NVT",
        "methods": (
            f"MD was performed with OpenMM 8.5 using the AMBER14 force field and TIP3P water. "
            f"Integration: LangevinMiddle, dt = 0.002 ps, constraints = h-bonds. "
            f"Nonbonded: PME (1.0 nm cutoff). Ensemble: NVT, 300 K. "
            f"Production length: {n_steps * 0.002:.1f} ps."
        ),
    }
    (out / "methods.json").write_text(json.dumps(methods, indent=2))
    print(f"openmm run complete -> {out} ({modeller.topology.getNumResidues()} residues)")


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2])
