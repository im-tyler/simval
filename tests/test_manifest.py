import numpy as np
from pathlib import Path

import pytest

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


# --- PYS-001: solver convergence is a mandatory, verdict-bearing check ---
# Stub pattern: the pyscf engine module imports pyscf lazily, so these
# pipeline-wiring tests run without the optional dependency installed.


def test_scf_converged_flag_check_passes_and_fails():
    from simval.pyscf_eng import check_scf_converged

    ok = check_scf_converged(True)
    assert ok.passed and ok.name == "scf_converged"
    bad = check_scf_converged(False)
    assert not bad.passed and bad.value == 0.0


def test_unconverged_scf_fails_pipeline_regardless_of_delta():
    from simval.pipeline import run_checks

    ctx = _ctx()
    # A flat energy sequence (final delta 0.0) with converged=False: the
    # delta check passes, the mandatory flag check must still fail.
    ctx.extra = {
        "scf_energies": [-1.1167593073964255, -1.1167593073964255],
        "final_energy": -1.1167593073964255,
        "n_electrons": 2,
        "converged": False,
    }
    results = run_checks(ctx)
    by_name = {r.name: r for r in results}
    assert by_name["scf_convergence"].passed is True
    assert by_name["scf_converged"].passed is False
    assert by_name["energy_sane"].passed is True
    assert build_manifest({}, results)["verdict"] == "fail"


def test_converged_scf_passes_pipeline_checks():
    from simval.pipeline import run_checks

    ctx = _ctx()
    ctx.extra = {
        "scf_energies": [-1.1167593073964255, -1.1167593073964255],
        "final_energy": -1.1167593073964255,
        "n_electrons": 2,
        "converged": True,
    }
    results = run_checks(ctx)
    assert all(
        r.passed for r in results if r.name.startswith("scf_") or r.name == "energy_sane"
    )


# --- IO-001: unique input selection + consumed-input provenance ---


def test_two_candidate_trajectories_rejected(tmp_path):
    # Filesystem-order dependent first-match used to pick one silently.
    from simval.context import GromacsEngine

    run = tmp_path / "amb"
    run.mkdir()
    (run / "a.xtc").write_bytes(b"0")
    (run / "b.xtc").write_bytes(b"0")
    (run / "conf.gro").write_bytes(b"0")
    with pytest.raises(ValueError, match="ambiguous trajectory"):
        GromacsEngine().load_context(run, selection="protein")


def test_two_topologies_rejected(tmp_path):
    from simval.context import GromacsEngine

    run = tmp_path / "amb"
    run.mkdir()
    (run / "a.gro").write_bytes(b"0")
    (run / "b.pdb").write_bytes(b"0")
    (run / "traj.xtc").write_bytes(b"0")
    with pytest.raises(ValueError, match="ambiguous topology"):
        GromacsEngine().load_context(run, selection="protein")


def test_manifest_hashes_all_consumed_synthetic_inputs(tmp_path):
    import numpy as np

    from simval.fixtures import make_run_dir
    from simval.manifest import verify_manifest, write_manifest
    from simval.pipeline import diagnose

    run = make_run_dir(tmp_path / "good", good=True)
    manifest = diagnose(run)
    hashed = set(manifest["files"])
    assert hashed >= {
        str(run / "energy.npy"),
        str(run / "positions.npy"),
        str(run / "reference.npy"),
        str(run / "params.json"),
    }
    out = tmp_path / "prov.json"
    write_manifest(manifest, out)
    assert verify_manifest(out)["ok"] is True

    np.save(run / "positions.npy", np.zeros((4, 3, 3)))  # tamper a consumed input
    tampered = verify_manifest(out)
    assert tampered["ok"] is False
    assert str(run / "positions.npy") in tampered["tampered"]


def test_artifact_paths_canonically_sorted(tmp_path):
    from simval.fixtures import make_run_dir
    from simval.pipeline import diagnose

    run = make_run_dir(tmp_path / "s", good=True)
    manifest = diagnose(run)
    assert list(manifest["files"]) == sorted(manifest["files"])


def test_ontos_run_tracks_stream_and_meta_inputs(tmp_path):
    import shutil

    from simval.context import select_engine

    run = tmp_path / "ontos_run"
    shutil.copytree(
        Path(__file__).parent.parent / "examples" / "ontos" / "r_pentomino", run
    )
    ctx = select_engine(run).load_context(run, selection="default")
    assert {p.name for p in ctx.consumed_inputs} == {"ontos.stream", "ontos.json"}


# --- DET-001: canonical digest independent of volatile execution metadata ---


def test_identical_verifications_share_canonical_digest(tmp_path):
    from simval.fixtures import make_run_dir
    from simval.pipeline import diagnose

    run = make_run_dir(tmp_path / "a", good=True, seed=7)
    m1 = diagnose(run)
    m2 = diagnose(run)  # identical verification, different created_at
    assert m1["created_at"] is not None
    assert m1["canonical_digest"] == m2["canonical_digest"]
    from simval.manifest import canonical_digest

    assert canonical_digest(m1) == m1["canonical_digest"]
    m1["files"]["fake.npy"] = "0" * 64
    assert canonical_digest(m1) != m1["canonical_digest"]


def test_orchestrate_results_digest_ignores_wall_times():
    from simval.manifest import canonical_digest

    rows_a = [{"run": "x", "mismatch_count": 0, "wall_s": 1.5, "gen_wall_s": 0.2}]
    rows_b = [{"run": "x", "mismatch_count": 0, "wall_s": 9.9, "gen_wall_s": 3.0}]
    assert canonical_digest({"runs": rows_a}) == canonical_digest({"runs": rows_b})
    rows_c = [{"run": "x", "mismatch_count": 1, "wall_s": 1.5}]
    assert canonical_digest({"runs": rows_a}) != canonical_digest({"runs": rows_c})
