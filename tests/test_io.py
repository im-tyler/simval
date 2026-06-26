import numpy as np
import pytest

pytest.importorskip("MDAnalysis")
datafiles = pytest.importorskip("MDAnalysisTests.datafiles")

from simval import io
from simval.diagnostics.ff_coverage import check_ff_coverage
from simval.diagnostics.rmsd import rmsd_over_time


def test_load_trajectory_protein_selection():
    positions, reference, names = io.load_trajectory(datafiles.XTC, datafiles.GRO, selection="protein")
    assert positions.ndim == 3
    assert positions.shape[0] >= 2
    assert positions.shape[2] == 3
    assert len(names) == positions.shape[1]
    series = rmsd_over_time(positions, reference)
    assert series.max() < 5.0
    assert np.all(series >= 0)


def test_naive_all_atom_rmsd_is_unphysical():
    positions, reference, _ = io.load_trajectory(datafiles.XTC, datafiles.GRO, selection="")
    series = rmsd_over_time(positions, reference)
    assert series.max() > 4.0


def test_load_real_force_field_atom_types():
    types = io.load_atom_types(datafiles.TPR, selection="protein")
    assert len(types) > 0
    assert all(t.startswith("opls") for t in types)


def test_ff_coverage_on_real_types():
    types = io.load_atom_types(datafiles.TPR, selection="protein")
    unique = sorted(set(types))
    ff_set = [t for t in unique if t not in {unique[0], unique[-1]}]
    result = check_ff_coverage(types, ff_set)
    assert result.passed is False
    assert unique[0] in result.detail["missing_atom_types"]
    assert unique[-1] in result.detail["missing_atom_types"]


def test_energy_xvg_parser(tmp_path):
    xvg = tmp_path / "energy.xvg"
    xvg.write_text(
        "# created\n"
        '@    xaxis label "Time (ps)"\n'
        '@    yaxis label "Energy (kJ/mol)"\n'
        '@ s0 legend "Total Energy"\n'
        "0.0 -12345.0\n1.0 -12344.5\n2.0 -12345.2\n3.0 -12344.8\n"
    )
    e = io.load_energy_xvg(xvg)
    assert len(e) == 4
    assert abs(e[0] - -12345.0) < 1e-6
    legend_map = io.load_energy_xvg(xvg, column=None)
    assert "Total Energy" in legend_map


def test_xvg_rejects_empty(tmp_path):
    xvg = tmp_path / "empty.xvg"
    xvg.write_text('@ s0 legend "X"\n# nothing\n')
    with pytest.raises(ValueError):
        io.load_energy_xvg(xvg)
