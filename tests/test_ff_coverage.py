from simval.diagnostics.ff_coverage import check_ff_coverage
from simval.fixtures import BAD_ATOM_TYPES, FF_ATOM_TYPES, GOOD_ATOM_TYPES


def test_full_coverage_passes():
    result = check_ff_coverage(GOOD_ATOM_TYPES, FF_ATOM_TYPES)
    assert result.passed is True
    assert result.value == 0


def test_missing_atom_types_fail_and_listed():
    result = check_ff_coverage(BAD_ATOM_TYPES, FF_ATOM_TYPES)
    assert result.passed is False
    assert "XX" in result.detail["missing_atom_types"]
    assert "ZZ" in result.detail["missing_atom_types"]
    assert result.detail["n_missing"] == 2


def test_missing_residue_detected():
    result = check_ff_coverage(
        GOOD_ATOM_TYPES, FF_ATOM_TYPES,
        system_residues=["ALA", "GLY", "LIG"],
        ff_residues=["ALA", "GLY"],
    )
    assert result.passed is False
    assert "LIG" in result.detail["missing_residues"]


# --- FF-001: unexpected topology parse failures fail ff_coverage ---


def test_load_atom_types_typed_tpr_unavailable_returns_empty(monkeypatch, tmp_path):
    # Stub pattern: an MDAnalysis TPR reader refusing a version signals it
    # with an IOError naming the tpr — that is the typed not-available case.
    import sys
    import types as types_mod

    from simval import io

    class _RefusingUniverse:
        def __init__(self, path):
            raise IOError("TPR files produced with beta versions of gromacs 2020 are not supported.")

    fake = types_mod.ModuleType("MDAnalysis")
    fake.Universe = _RefusingUniverse
    monkeypatch.setitem(sys.modules, "MDAnalysis", fake)
    tpr = tmp_path / "topol.tpr"
    tpr.write_bytes(b"junk")
    assert io.load_atom_types(tpr) == []


def test_load_atom_types_unexpected_error_propagates(monkeypatch, tmp_path):
    import sys
    import types as types_mod

    from simval import io

    class _BrokenUniverse:
        def __init__(self, path):
            raise RuntimeError("parser exploded")

    fake = types_mod.ModuleType("MDAnalysis")
    fake.Universe = _BrokenUniverse
    monkeypatch.setitem(sys.modules, "MDAnalysis", fake)
    tpr = tmp_path / "topol.tpr"
    tpr.write_bytes(b"junk")
    import pytest

    with pytest.raises(RuntimeError, match="parser exploded"):
        io.load_atom_types(tpr)


def test_ff_load_error_fails_ff_coverage_when_applicable(monkeypatch, tmp_path):
    # Force a parser exception with ff_atom_types.txt present: the
    # diagnosis must fail on ff_coverage (audit FF-001).
    from simval import io as io_mod
    from simval.context import GromacsEngine
    from simval.pipeline import run_checks

    def boom(top, **k):
        raise RuntimeError("tpr parse exploded")

    monkeypatch.setattr(io_mod, "load_atom_types", boom)
    run = tmp_path / "gromacs"
    run.mkdir()
    (run / "topol.tpr").write_bytes(b"junk")
    (run / "ff_atom_types.txt").write_text("C\nCA\nN\n")

    ctx = GromacsEngine().load_context(run, selection="protein")
    assert "ff_load_error" in ctx.extra
    results = run_checks(ctx)
    errored = [r for r in results if r.name == "ff_coverage"]
    assert errored and not errored[0].passed
    assert "tpr parse exploded" in errored[0].detail["error"]


def test_ff_load_error_without_ff_list_not_applicable(monkeypatch, tmp_path):
    from simval import io as io_mod
    from simval.context import GromacsEngine
    from simval.pipeline import run_checks

    def boom(top, **k):
        raise RuntimeError("tpr parse exploded")

    monkeypatch.setattr(io_mod, "load_atom_types", boom)
    run = tmp_path / "gromacs"
    run.mkdir()
    (run / "topol.tpr").write_bytes(b"junk")

    ctx = GromacsEngine().load_context(run, selection="protein")
    results = run_checks(ctx)
    assert not any(r.name == "ff_coverage" for r in results)
