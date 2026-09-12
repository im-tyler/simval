import numpy as np

from simval.diagnostics.energy import check_energy_drift
from simval.fixtures import drifting_energy_series, good_energy_series


def test_good_energy_passes():
    result = check_energy_drift(good_energy_series())
    assert result.passed is True
    assert result.name == "energy_drift"
    assert result.value < result.threshold


def test_drifting_energy_fails():
    result = check_energy_drift(drifting_energy_series())
    assert result.passed is False
    assert result.value > result.threshold


def test_skip_fraction_discards_transient():
    series = good_energy_series(n=1000).copy()
    series[:100] += np.linspace(800.0, 0.0, 100)
    result = check_energy_drift(series, skip_fraction=0.1)
    assert result.passed is True


def test_transient_without_skip_fails():
    series = good_energy_series(n=1000).copy()
    series[:100] += np.linspace(800.0, 0.0, 100)
    result = check_energy_drift(series, skip_fraction=0.0)
    assert result.passed is False


def test_result_serializes():
    result = check_energy_drift(good_energy_series())
    d = result.to_dict()
    assert set(d) == {"name", "passed", "threshold", "value", "detail"}
    assert isinstance(result.detail["slope_per_step"], float)


def test_rejects_short_input():
    import pytest

    with pytest.raises(ValueError):
        check_energy_drift(np.array([1.0]))


# --- IO-002: a conserved-energy column must be labeled, never positional ---


def test_engine_records_explicit_skip_when_xvg_lacks_conserved_label(tmp_path):
    # A trajectory-less run-dir: the xvg is still consumed, and without a
    # labeled conserved column the energy check must be an explicit skip,
    # never a positional first-column fallback (audit IO-002).
    from simval.context import GromacsEngine

    run = tmp_path / "run"
    run.mkdir()
    (run / "energy.xvg").write_text(
        '@ s0 legend "Temperature"\n0.0 300.0\n1.0 301.0\n2.0 300.5\n'
    )
    ctx = GromacsEngine().load_context(run, selection="protein")
    assert ctx.energy is None
    assert "no conserved-energy column" in ctx.skipped["energy"]


# --- IO-003: malformed xvg data fails; only a typed missing label may skip ---


def test_malformed_nonnumeric_row_rejected_with_context(tmp_path):
    import pytest

    from simval.io import XvgParseError, load_energy_xvg

    xvg = tmp_path / "energy.xvg"
    xvg.write_text(
        '@ s0 legend "Total Energy"\n'
        "0.0 -12345.0\n"
        "1.0 -12344.oops\n"
    )
    with pytest.raises(XvgParseError, match=r"line 3 column 2.*oops"):
        load_energy_xvg(xvg)


def test_ragged_numeric_row_rejected(tmp_path):
    import pytest

    from simval.io import XvgParseError, load_energy_xvg

    xvg = tmp_path / "energy.xvg"
    xvg.write_text(
        '@ s0 legend "Temperature"\n@ s1 legend "Total Energy"\n'
        "0.0 300.0 -12345.0\n"
        "1.0 301.0\n"
    )
    with pytest.raises(XvgParseError, match="ragged data row with 2 columns"):
        load_energy_xvg(xvg, column=None)


def test_missing_label_well_formed_is_the_typed_skip(tmp_path):
    import pytest

    from simval.io import ConservedEnergyColumnMissing, load_preferred_energy

    xvg = tmp_path / "energy.xvg"
    xvg.write_text('@ s0 legend "Temperature"\n0.0 300.0\n1.0 301.0\n')
    with pytest.raises(ConservedEnergyColumnMissing, match="no conserved-energy column"):
        load_preferred_energy(xvg)


def test_malformed_row_fails_energy_diagnostic(tmp_path):
    # Through the engine path: a present-but-malformed energy file must
    # surface as a failing energy_drift result, never a skip (IO-003).
    from simval.context import GromacsEngine
    from simval.pipeline import run_checks

    run = tmp_path / "run"
    run.mkdir()
    (run / "energy.xvg").write_text(
        '@ s0 legend "Total Energy"\n0.0 -12345.0\n1.0 nan_is_not_written_like_this\n'
    )
    ctx = GromacsEngine().load_context(run, selection="protein")
    assert ctx.energy is None
    assert "energy" not in ctx.skipped
    assert "energy_load_error" in ctx.extra
    results = run_checks(ctx)
    errored = [r for r in results if r.name == "energy_drift"]
    assert errored and not errored[0].passed
    assert "XvgParseError" in errored[0].detail["error"]


def test_ragged_row_fails_energy_diagnostic(tmp_path):
    from simval.context import GromacsEngine
    from simval.pipeline import run_checks

    run = tmp_path / "run"
    run.mkdir()
    (run / "energy.xvg").write_text(
        '@ s0 legend "Temperature"\n@ s1 legend "Total Energy"\n0.0 300.0 -1.0\n1.0 301.0\n'
    )
    ctx = GromacsEngine().load_context(run, selection="protein")
    assert ctx.energy is None
    assert "energy" not in ctx.skipped
    results = run_checks(ctx)
    errored = [r for r in results if r.name == "energy_drift"]
    assert errored and not errored[0].passed
    assert "ragged" in errored[0].detail["error"]


def test_missing_label_records_explicit_skip_not_error(tmp_path):
    from simval.context import GromacsEngine
    from simval.pipeline import run_checks

    run = tmp_path / "run"
    run.mkdir()
    (run / "energy.xvg").write_text('@ s0 legend "Temperature"\n0.0 300.0\n1.0 301.0\n')
    ctx = GromacsEngine().load_context(run, selection="protein")
    assert ctx.energy is None
    assert "energy" in ctx.skipped
    assert "energy_load_error" not in ctx.extra
    results = run_checks(ctx)
    assert not any(r.name == "energy_drift" for r in results)
