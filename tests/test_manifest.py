import numpy as np

from simval.diagnostics.energy import check_energy_drift
from simval.fixtures import drifting_energy_series, good_energy_series
from simval.manifest import build_manifest, compute_hashes, load_manifest, write_manifest


def test_pass_manifest_verdict_pass():
    result = check_energy_drift(good_energy_series())
    manifest = build_manifest({}, [result])
    assert manifest["verdict"] == "pass"
    assert manifest["schema"] == "simval.provenance.v1"
    assert manifest["tier2_signed_off"] is False


def test_fail_manifest_verdict_fail():
    result = check_energy_drift(drifting_energy_series())
    manifest = build_manifest({}, [result])
    assert manifest["verdict"] == "fail"
    assert manifest["diagnostics"][0]["name"] == "energy_drift"


def test_round_trip_with_hashes(tmp_path):
    f = tmp_path / "energy.npy"
    np.save(f, good_energy_series())
    result = check_energy_drift(good_energy_series())
    manifest = build_manifest({}, [result], files=[f])
    out = tmp_path / "provenance.json"
    write_manifest(manifest, out)
    loaded = load_manifest(out)
    assert loaded["verdict"] == manifest["verdict"]
    assert str(f) in loaded["files"]
    assert loaded["files"][str(f)] == compute_hashes([f])[str(f)]


def test_verify_manifest_detects_tampering(tmp_path):
    import numpy as np

    f = tmp_path / "energy.npy"
    np.save(f, good_energy_series())
    result = check_energy_drift(good_energy_series())
    manifest = build_manifest({}, [result], files=[f])
    out = tmp_path / "provenance.json"
    write_manifest(manifest, out)

    from simval.manifest import verify_manifest
    ok = verify_manifest(out)
    assert ok["ok"] is True

    np.save(f, drifting_energy_series())  # tamper
    tampered = verify_manifest(out)
    assert tampered["ok"] is False
    assert tampered["tampered"]


# --- PIPE-001: errored applicable diagnostics block the verdict ---


def _ctx(**over):
    from pathlib import Path

    from simval.context import RunContext

    ctx = RunContext(run_dir=Path("/tmp/x"), engine="gromacs", selection="protein")
    for k, v in over.items():
        setattr(ctx, k, v)
    return ctx


def test_errored_rmsf_check_fails_and_names_diagnostic(monkeypatch):
    from simval import pipeline
    from simval.diagnostics import rmsf as rmsf_mod

    def boom(*a, **k):
        raise RuntimeError("rmsf exploded")

    monkeypatch.setattr(rmsf_mod, "check_rmsf", boom)
    import numpy as np

    ctx = _ctx(
        ca_positions=np.zeros((2, 3, 3)),
        ca_reference=np.zeros((3, 3)),
    )
    results = pipeline.run_checks(ctx)
    errored = [r for r in results if r.name == "per_residue_rmsf"]
    assert errored and not errored[0].passed
    assert errored[0].detail["status"] == "error"
    assert "rmsf exploded" in errored[0].detail["error"]
    manifest = build_manifest({}, results)
    assert manifest["verdict"] == "fail"


def test_ca_load_error_fails_manifest_naming_rmsf():
    from simval import pipeline

    ctx = _ctx()
    ctx.extra["ca_load_error"] = "RuntimeError: trajectory exploded"
    results = pipeline.run_checks(ctx)
    errored = [r for r in results if r.name == "per_residue_rmsf"]
    assert errored and not errored[0].passed
    assert build_manifest({}, results)["verdict"] == "fail"


def test_errored_charge_state_and_hbonds_fail_manifest(monkeypatch, tmp_path):
    from simval import pipeline
    from simval.diagnostics import hbonds as hbonds_mod
    from simval.diagnostics import prep as prep_mod

    def boom(*a, **k):
        raise RuntimeError("diagnostic exploded")

    monkeypatch.setattr(prep_mod, "check_charge_state", boom)
    monkeypatch.setattr(hbonds_mod, "check_hydrogen_bonds", boom)
    ctx = _ctx(
        structure_path=tmp_path / "s.gro",
        tpr_path=tmp_path / "t.tpr",
        trajectory_path=tmp_path / "t.xtc",
    )
    results = pipeline.run_checks(ctx)
    names = {r.name for r in results if not r.passed}
    assert {"charge_state", "hydrogen_bonds"} <= names
    assert build_manifest({}, results)["verdict"] == "fail"


def test_optional_dependency_absence_is_explicit_skip(monkeypatch, tmp_path):
    from simval import pipeline
    from simval.diagnostics import prep as prep_mod

    def missing(*a, **k):
        raise ImportError("No module named 'gmx'")

    monkeypatch.setattr(prep_mod, "check_charge_state", missing)
    ctx = _ctx(
        structure_path=tmp_path / "s.gro",
        tpr_path=tmp_path / "t.tpr",
    )
    results = pipeline.run_checks(ctx)
    assert not any(r.name == "charge_state" and not r.passed for r in results)
    assert "charge_state" in ctx.skipped
    assert "optional dependency" in ctx.skipped["charge_state"]
