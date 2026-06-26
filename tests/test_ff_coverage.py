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
