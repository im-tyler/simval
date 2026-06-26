import MDAnalysis as mda
import pytest

datafiles = pytest.importorskip("MDAnalysisTests.datafiles", reason="needs datafiles")


def test_engine_reads_dcd_and_pdb(tmp_path):
    """The MD adapter is format-agnostic: reads .pdb + .dcd (OpenMM/AMBER/NAMD),
    not just .gro + .xtc (GROMACS). Proves a second MD engine through one port."""
    u = mda.Universe(datafiles.GRO, datafiles.XTC)
    run = tmp_path / "dcd_run"
    run.mkdir()
    u.atoms.write(run / "topology.pdb")
    with mda.Writer(str(run / "traj.dcd"), n_atoms=u.atoms.n_atoms) as w:
        for _ts in u.trajectory:
            w.write(u.atoms)

    from simval.context import GromacsEngine, select_engine
    from simval.oracle.validate import compute_metrics

    eng = select_engine(run)
    assert isinstance(eng, GromacsEngine)
    metrics = compute_metrics(run, selection="protein and name CA")
    assert metrics["n_frames"] == 10
    assert metrics["n_selected_atoms"] == 214
