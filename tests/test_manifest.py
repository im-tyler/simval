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
