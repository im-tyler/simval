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


# --- IO-002: no positional fallback for the conserved-energy column ---


def test_preferred_energy_prefers_conserved_label(tmp_path):
    xvg = tmp_path / "energy.xvg"
    xvg.write_text(
        '@ s0 legend "Temperature"\n'
        '@ s1 legend "Conserved En."\n'
        "0.0 300.0 -12345.0\n1.0 301.0 -12344.5\n"
    )
    term, arr = io.load_preferred_energy(xvg)
    assert term == "Conserved En."
    assert arr[0] == -12345.0


def test_preferred_energy_missing_label_is_error_not_first_column(tmp_path):
    # The old fallback would return the first non-time column (here
    # Temperature), silently drift-checking a non-conserved quantity.
    xvg = tmp_path / "energy.xvg"
    xvg.write_text(
        '@ s0 legend "Temperature"\n'
        '@ s1 legend "Box-X"\n'
        "0.0 300.0 4.0\n1.0 301.0 4.0\n"
    )
    with pytest.raises(ValueError, match="no conserved-energy column"):
        io.load_preferred_energy(xvg)


def test_preferred_energy_unlabeled_columns_rejected(tmp_path):
    xvg = tmp_path / "energy.xvg"
    xvg.write_text("0.0 -12345.0\n1.0 -12344.5\n")
    with pytest.raises(ValueError, match="no conserved-energy column"):
        io.load_preferred_energy(xvg)


def test_preferred_energy_documented_aliases(tmp_path):
    for alias in io.CONSERVED_ENERGY_ALIASES:
        xvg = tmp_path / "energy.xvg"
        xvg.write_text(f'@ s0 legend "{alias}"\n0.0 -12345.0\n1.0 -12344.5\n')
        term, arr = io.load_preferred_energy(xvg)
        assert term == alias
