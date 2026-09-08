"""Ontos gravity adapter tests: independent spec reimplementation vs recorded streams."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest

from simval.context import select_engine
from simval.ontos_gravity import (
    UNMANAGED,
    GravityWorld,
    SplitMix64,
    check_bounded_drift,
    check_collapse_energy,
    check_multipole_match,
    check_reconstruction_error,
    check_reference_match_gravity,
    region_at,
    verify_stream_gravity,
)
from simval.pipeline import run_checks

EXAMPLES = Path(__file__).parent.parent / "examples" / "ontos_gravity"

CASES = [
    ("all_fine", 42, 100),
    ("window", 42, 120),
    ("refit", 7, 120),
    ("multi", 3, 150),
    ("observer", 5, 300),
]


@pytest.mark.parametrize("name,seed,ticks", CASES)
def test_reference_matches_stream(name, seed, ticks):
    summary = verify_stream_gravity(EXAMPLES / name / "ontos.stream", seed)
    assert summary["mismatch_count"] == 0
    assert summary["ticks_verified"] == ticks
    assert check_reference_match_gravity(summary).passed
    assert check_bounded_drift(summary).passed


def test_all_fine_conserves_momentum_exactly():
    from simval.ontos_gravity import GravityWorld

    world = GravityWorld(5, 6)
    px0, py0 = world.px, world.py
    for _ in range(60):
        world.step()
    assert world.px == px0
    assert world.py == py0


def test_splitmix64_deterministic_and_spread():
    a = SplitMix64(123)
    b = SplitMix64(123)
    vals = [a.next() for _ in range(64)]
    assert vals == [b.next() for _ in range(64)]
    assert len(set(vals)) == 64


def test_corrupted_body_state_fails(tmp_path):
    data = bytearray((EXAMPLES / "all_fine" / "ontos.stream").read_bytes())
    _, records = __import__("simval.ontos_gravity", fromlist=["parse_stream_v2"]).parse_stream_v2(
        EXAMPLES / "all_fine" / "ontos.stream"
    )
    offset = 20
    for record in records:
        size = {
            "tick": 9,
            "snapshot": 9,
            "flip": 17,
            "level": 10,
            "state": 34,
            "body": 55,
            "totals": 57,
            "multipole": 57,
        }[record[0]]
        if record[0] == "body":
            data[offset + size - 9] ^= 0x01
            break
        offset += size
    corrupt = tmp_path / "ontos.stream"
    corrupt.write_bytes(bytes(data))
    summary = verify_stream_gravity(corrupt, 42)
    assert summary["mismatch_count"] > 0
    assert not check_reference_match_gravity(summary).passed


def test_engine_detect_and_diagnose_gravity(tmp_path):
    import shutil

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "window", run)
    engine = select_engine(run)
    assert engine.name == "ontos"
    ctx = engine.load_context(run, selection="default")
    results = run_checks(ctx)
    names = {r.name for r in results}
    assert "ontos_reference_match" in names
    assert "ontos_window_drift" in names
    assert all(r.passed for r in results if r.name.startswith("ontos_"))


def test_wrong_seed_fails(tmp_path):
    import shutil

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "window", run)
    summary = verify_stream_gravity(run / "ontos.stream", 43)
    assert summary["mismatch_count"] > 0


def test_zoom_policy_matches_and_detects_tampering(tmp_path):
    import shutil

    from simval.ontos_gravity import check_zoom_policy, parse_stream_v2

    _, records = parse_stream_v2(EXAMPLES / "observer" / "ontos.stream")
    result = check_zoom_policy(records, 5, 777)
    assert result.passed, result.detail
    assert result.detail["policy_events"] >= 3

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "observer", run)
    data = bytearray((run / "ontos.stream").read_bytes())
    sizes = {1: 9, 2: 9, 3: 17, 4: 10, 5: 34, 6: 55, 7: 57}
    off = 20
    flipped = False
    while off < len(data):
        tag = data[off]
        if tag == 4 and not flipped:
            data[off + 9] ^= 0x01
            flipped = True
            break
        off += sizes[tag]
    (run / "ontos.stream").write_bytes(bytes(data))
    _, records = parse_stream_v2(run / "ontos.stream")
    result = check_zoom_policy(records, 5, 777)
    assert not result.passed


def test_observer_engine_diagnose(tmp_path):
    import shutil

    from simval.context import select_engine as sel
    from simval.pipeline import run_checks as rc

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "observer", run)
    engine = sel(run)
    ctx = engine.load_context(run, selection="default")
    results = rc(ctx)
    names = {r.name for r in results}
    assert "ontos_zoom_policy" in names
    zoom = next(r for r in results if r.name == "ontos_zoom_policy")
    assert zoom.passed


def test_rebound_anchor_agrees():
    rebound = pytest.importorskip("rebound")
    from simval.ontos_gravity import check_rebound_anchor, parse_stream_v2

    _, records = parse_stream_v2(EXAMPLES / "all_fine" / "ontos.stream")
    result = check_rebound_anchor(records, 42, 8)
    assert result.passed, result.detail
    assert result.value < 1e-4


# --- Section 19: collapse and reconstruction ---


def _emit_gravity_stream(path, seed, count, schedule, ticks):
    """Serialize a reference gravity run per the spec section 16 emission contract.

    schedule: list of (tick, region_index, level) with level 0 demote,
    1 promote/expand, 2 collapse. Collapse events additionally emit the
    section 19 RegionCollapsed record before that tick's TickHeader.
    """
    world = GravityWorld(seed, count)
    out = bytearray(b"ONTO")
    out += struct.pack("<IIII", 2, 128, 128, count)
    events = {}
    for t, region, level in schedule:
        world.schedule(t, region, level)
        events.setdefault(t, []).append((region, level))
    for _ in range(ticks):
        entering = world.tick + 1
        for region, level in events.get(entering, []):
            out += b"\x04" + struct.pack("<IIB", region % 2, region // 2, level)
        world.step()
        for c in world.last_collapses:
            out += b"\x08" + struct.pack(
                "<QIIQdddddd",
                c["tick"],
                c["region"] % 2,
                c["region"] // 2,
                c["count"],
                c["mass"],
                c["com_x"],
                c["com_y"],
                c["px"],
                c["py"],
                c["energy"],
            )
            if c["multipole"]:
                out += b"\x09" + struct.pack(
                    "<QIIddddd",
                    c["tick"],
                    c["region"] % 2,
                    c["region"] // 2,
                    c["mx"],
                    c["my"],
                    c["qxx"],
                    c["qxy"],
                    c["qyy"],
                )
        world.last_collapses.clear()
        out += b"\x01" + struct.pack("<Q", world.tick)
        out += b"\x02" + struct.pack("<Q", count)
        fine, coarse_n, mass, px, py, energy = world.totals()
        out += b"\x07" + struct.pack("<QQQdddd", world.tick, fine, coarse_n, mass, px, py, energy)
        for rx, ry in ((0, 0), (1, 0), (0, 1), (1, 1)):
            level, pop, rhash = world.region_hash(ry * 2 + rx)
            out += b"\x05" + struct.pack("<QIIBQQ", world.tick, rx, ry, level, pop, rhash)
        for i in range(count):
            b, region, level = world.emitted_state(i)
            out += b"\x06" + struct.pack(
                "<QIBBddddd", world.tick, i, region, level, b["x"], b["y"], b["vx"], b["vy"], b["mass"]
            )
    Path(path).write_bytes(bytes(out))
    return world


def _region_occupancy(seed, count, at_tick):
    world = GravityWorld(seed, count)
    for _ in range(at_tick):
        world.step()
    counts = [0, 0, 0, 0]
    for b in world.bodies:
        r = region_at(b["x"], b["y"])
        if r != UNMANAGED:
            counts[r] += 1
    return sorted(range(4), key=lambda r: -counts[r]), counts


@pytest.mark.parametrize(
    "name,seed,count,schedule,ticks",
    [
        ("all_fine", 42, 8, [], 100),
        ("window", 42, 8, [(20, 0, 0), (80, 0, 1)], 120),
        ("refit", 7, 12, [(5, 3, 0)], 120),
        ("multi", 3, 10, [(10, 2, 0), (40, 2, 0), (100, 2, 1)], 150),
    ],
)
def test_emitter_reproduces_recorded_streams(tmp_path, name, seed, count, schedule, ticks):
    out = tmp_path / f"{name}.stream"
    _emit_gravity_stream(out, seed, count, schedule, ticks)
    assert out.read_bytes() == (EXAMPLES / name / "ontos.stream").read_bytes()


@pytest.mark.parametrize("seed,count", [(42, 8), (7, 12), (3, 10), (5, 16)])
def test_collapse_expand_roundtrip_self_consistent(tmp_path, seed, count):
    order, counts = _region_occupancy(seed, count, 5)
    region = order[0]
    assert counts[region] >= 2
    stream = tmp_path / f"collapse_{seed}.stream"
    _emit_gravity_stream(stream, seed, count, [(6, region, 2), (36, region, 1)], 80)
    summary = verify_stream_gravity(stream, seed)
    assert summary["mismatch_count"] == 0, summary["mismatches"]
    assert summary["collapse_events"] == 1
    assert summary["expand_events"] == 1
    assert summary["ticks_verified"] == 80
    assert check_reference_match_gravity(summary).passed
    # Measured across these seeds: post-expansion deviation 10.3-22.2
    # (tolerance 64.0), collapse-energy relative delta 0.46-3.49 (tolerance 8.0),
    # tracked-body window drift pos<=5.3e-5 mom<=4.4e-3 energy<=4.9e-4.
    assert check_reconstruction_error(summary).passed
    assert 0.0 < summary["post_expansion_deviation"] < 64.0
    assert check_collapse_energy(summary).passed
    assert check_collapse_energy(summary).value < 8.0
    assert check_bounded_drift(summary).passed


def test_multi_region_collapse_with_window(tmp_path):
    # seed 42, 8 bodies: occupancy at tick 5 is [3, 0, 3, 2] -> order [0, 2, 3, 1]
    order, _ = _region_occupancy(42, 8, 5)
    schedule = [
        (6, order[0], 2),
        (10, order[1], 2),
        (14, order[2], 0),
        (40, order[0], 1),
    ]
    stream = tmp_path / "multi_collapse.stream"
    _emit_gravity_stream(stream, 42, 8, schedule, 70)
    summary = verify_stream_gravity(stream, 42)
    assert summary["mismatch_count"] == 0, summary["mismatches"]
    assert summary["collapse_events"] == 2
    assert summary["expand_events"] == 1
    assert check_reconstruction_error(summary).passed
    assert check_collapse_energy(summary).passed
    # 6 of 8 bodies collapsed for most of the run: the two tracked bodies see
    # monopoles instead of real bodies. Measured tracked energy drift 1.2e-3
    # (above the 1e-3 single-window default, still small); bounded here.
    assert summary["energy_drift"] < 5e-3
    assert summary["momentum_drift"] < 5e-2


def test_collapsed_bodies_static_level2_real_mass():
    order, _ = _region_occupancy(42, 8, 5)
    region = order[0]
    world = GravityWorld(42, 8)
    world.schedule(6, region, 2)
    for _ in range(6):
        world.step()
    states = [world.emitted_state(i) for i in range(8)]
    collapsed = [(b, r) for b, r, lv in states if lv == 2]
    assert len(collapsed) >= 2
    for _ in range(12):
        world.step()
    after = [world.emitted_state(i) for i in range(8)]
    for (b1, r1, lv1), (b2, r2, lv2) in zip(states, after):
        if lv1 == 2:
            assert lv2 == 2 and r2 == r1 == region
            assert (b1["x"], b1["y"], b1["vx"], b1["vy"], b1["mass"]) == (
                b2["x"],
                b2["y"],
                b2["vx"],
                b2["vy"],
                b2["mass"],
            )
    ics = {b["id"]: b["mass"] for b in GravityWorld(42, 8).bodies}
    for b, _ in collapsed:
        assert b["mass"] == ics[b["id"]]


def test_expansion_residual_momentum_exact():
    order, _ = _region_occupancy(42, 8, 5)
    region = order[0]
    world = GravityWorld(42, 8)
    world.schedule(6, region, 2)
    for _ in range(6):
        world.step()
    world.schedule(36, region, 1)
    for _ in range(30):
        world.step()
    exp = world.last_expansion
    assert exp["tick"] == 36
    bodies = exp["bodies"]
    assert [b["id"] for b in bodies] == sorted(b["id"] for b in bodies)
    # last body velocity is the exact spec residual, bit for bit
    last = bodies[-1]
    sum_mvx = 0.0
    sum_mvy = 0.0
    for b in bodies[:-1]:
        sum_mvx += b["mass"] * b["vx"]
        sum_mvy += b["mass"] * b["vy"]
    assert struct.pack("<d", last["vx"]) == struct.pack("<d", (exp["target_px"] - sum_mvx) / last["mass"])
    assert struct.pack("<d", last["vy"]) == struct.pack("<d", (exp["target_py"] - sum_mvy) / last["mass"])
    # total reconstructed momentum closes on the collapse totals to rounding
    # (measured: 0.0 or ~1.4e-16 absolute at momentum scale ~0.7)
    px = 0.0
    py = 0.0
    for b in bodies:
        px += b["mass"] * b["vx"]
        py += b["mass"] * b["vy"]
    scale = max(abs(exp["target_px"]), abs(exp["target_py"]), 1e-30)
    assert max(abs(px - exp["target_px"]), abs(py - exp["target_py"])) / scale < 1e-12


def test_collapse_monopole_ledger_drift_bounded():
    # Measured over 30 collapsed ticks across seeds 42/7/3/5 (N=8..16):
    # relative ledger drift 1.0e-3 - 2.1e-3; bound at 1e-2 for margin.
    order, _ = _region_occupancy(42, 8, 5)
    world = GravityWorld(42, 8)
    world.schedule(6, order[0], 2)
    for _ in range(6):
        world.step()
    px0, py0 = world.px, world.py
    scale = max(abs(px0), abs(py0), 1e-30)
    for _ in range(30):
        world.step()
    drift = max(abs(world.px - px0), abs(world.py - py0)) / scale
    assert 0.0 < drift < 1e-2


def test_tampered_collapse_record_fails(tmp_path):
    order, _ = _region_occupancy(42, 8, 5)
    stream = tmp_path / "ontos.stream"
    _emit_gravity_stream(stream, 42, 8, [(6, order[0], 2), (36, order[0], 1)], 40)
    data = bytearray(stream.read_bytes())
    sizes = {1: 9, 2: 9, 3: 17, 4: 10, 5: 34, 6: 55, 7: 57, 8: 73, 9: 57}
    off = 20
    flipped = False
    while off < len(data):
        tag = data[off]
        if tag == 8 and not flipped:
            data[off + 33] ^= 0x01  # low byte of com_x
            flipped = True
            break
        off += sizes[tag]
    assert flipped
    corrupt = tmp_path / "corrupt.stream"
    corrupt.write_bytes(bytes(data))
    summary = verify_stream_gravity(corrupt, 42)
    assert summary["mismatch_count"] > 0
    assert not check_reference_match_gravity(summary).passed


def test_wrong_seed_fails_collapse_stream(tmp_path):
    order, _ = _region_occupancy(42, 8, 5)
    stream = tmp_path / "ontos.stream"
    _emit_gravity_stream(stream, 42, 8, [(6, order[0], 2), (36, order[0], 1)], 40)
    summary = verify_stream_gravity(stream, 43)
    assert summary["mismatch_count"] > 0
    assert not check_reference_match_gravity(summary).passed


def test_engine_diagnose_collapse_run(tmp_path):
    order, _ = _region_occupancy(42, 8, 5)
    run = tmp_path / "ontos_run"
    run.mkdir()
    _emit_gravity_stream(run / "ontos.stream", 42, 8, [(6, order[0], 2), (36, order[0], 1)], 80)
    (run / "ontos.json").write_text(json.dumps({"seed": 42}))
    engine = select_engine(run)
    assert engine.name == "ontos"
    ctx = engine.load_context(run, selection="default")
    results = run_checks(ctx)
    names = {r.name for r in results}
    assert "ontos_reconstruction_error" in names
    assert "ontos_collapse_energy" in names
    assert all(r.passed for r in results if r.name.startswith("ontos_"))


# --- Section 20: multipole reconstruction ---


def test_multipole_roundtrip_self_consistent(tmp_path):
    # The default world is multipole-on (section 20): collapses emit the
    # RegionMultipole record and expansions synthesize under dipole +
    # quadrupole constraints.
    order, counts = _region_occupancy(42, 8, 5)
    region = order[0]
    assert counts[region] >= 3
    stream = tmp_path / "multipole.stream"
    _emit_gravity_stream(stream, 42, 8, [(6, region, 2), (36, region, 1)], 80)
    summary = verify_stream_gravity(stream, 42)
    assert summary["mismatch_count"] == 0, summary["mismatches"]
    assert summary["collapse_events"] == 1
    assert summary["multipole_events"] == 1
    assert summary["expand_events"] == 1
    result = check_multipole_match(summary)
    assert result.passed, result.detail
    # Measured: dipole closes at 0.0, quadrupole matches ~1e-15.
    assert result.detail["worst_dipole_relative"] <= 1e-12
    assert result.detail["worst_quadrupole_relative"] <= 1e-9
    # Post-expansion deviation stays region-scale (same tier as section 19).
    assert check_reconstruction_error(summary).passed
    assert 0.0 < summary["post_expansion_deviation"] < 64.0


def test_multipole_recorded_stream_verifies():
    summary = verify_stream_gravity(EXAMPLES / "multipole" / "ontos.stream", 17)
    assert summary["mismatch_count"] == 0, summary["mismatches"]
    assert summary["ticks_verified"] == 240
    assert summary["collapse_events"] == 3
    assert summary["multipole_events"] == 3
    assert summary["expand_events"] == 3
    assert check_multipole_match(summary).passed


def test_legacy_section19_examples_still_verify():
    # Streams whose collapses carry no RegionMultipole record reconstruct
    # per section 19; the committed pre-section-20 examples must verify
    # bit-exactly.
    for name, seed in (("collapse", 11), ("collapse_observer", 13)):
        summary = verify_stream_gravity(EXAMPLES / name / "ontos.stream", seed)
        assert summary["mismatch_count"] == 0, summary["mismatches"]
        assert summary["multipole_events"] == 0
        assert check_multipole_match(summary).passed


def test_multipole_dipole_residual_exact():
    order, _ = _region_occupancy(42, 8, 5)
    region = order[0]
    world = GravityWorld(42, 8)
    world.schedule(6, region, 2)
    world.schedule(36, region, 1)
    for _ in range(36):
        world.step()
    exp = world.last_expansion
    assert exp is not None and exp["multipole"]
    sx = 0.0
    sy = 0.0
    for b in exp["bodies"]:
        sx += b["mass"] * b["x"]
        sy += b["mass"] * b["y"]
    scale = max(abs(exp["target_mx"]), abs(exp["target_my"]), 1e-30)
    assert max(abs(sx - exp["target_mx"]), abs(sy - exp["target_my"])) / scale < 1e-12
    # momentum residual unchanged from section 19
    px = 0.0
    py = 0.0
    for b in exp["bodies"]:
        px += b["mass"] * b["vx"]
        py += b["mass"] * b["vy"]
    scale = max(abs(exp["target_px"]), abs(exp["target_py"]), 1e-30)
    assert max(abs(px - exp["target_px"]), abs(py - exp["target_py"])) / scale < 1e-12


def test_multipole_quadrupole_matches_record():
    order, _ = _region_occupancy(7, 12, 5)
    region = order[0]
    world = GravityWorld(7, 12)
    world.schedule(6, region, 2)
    world.schedule(36, region, 1)
    for _ in range(36):
        world.step()
    exp = world.last_expansion
    assert exp is not None and exp["transformed"]
    qxx = 0.0
    qxy = 0.0
    qyy = 0.0
    for b in exp["bodies"]:
        dx = b["x"] - exp["target_com_x"]
        dy = b["y"] - exp["target_com_y"]
        qxx += b["mass"] * dx * dx
        qxy += b["mass"] * dx * dy
        qyy += b["mass"] * dy * dy
    scale = max(abs(exp["target_qxx"]), abs(exp["target_qyy"]), 1e-30)
    assert max(abs(qxx - exp["target_qxx"]), abs(qxy - exp["target_qxy"]), abs(qyy - exp["target_qyy"])) / scale < 1e-9


def test_multipole_single_body_pins_position():
    world = None
    for seed in range(100_000):
        w = GravityWorld(seed, 1)
        b = w.bodies[0]
        if 0.0 <= b["x"] < 64.0 and 0.0 <= b["y"] < 64.0:
            world = w
            break
    w = world
    w.schedule(1, 0, 2)
    w.schedule(10, 0, 1)
    for _ in range(10):
        w.step()
    exp = w.last_expansion
    assert exp is not None and exp["multipole"] and not exp["transformed"]
    b = exp["bodies"][0]
    scale = max(abs(exp["target_mx"]), abs(exp["target_my"]), 1e-30)
    assert max(abs(b["mass"] * b["x"] - exp["target_mx"]), abs(b["mass"] * b["y"] - exp["target_my"])) / scale < 1e-12


def test_tampered_multipole_record_fails(tmp_path):
    order, _ = _region_occupancy(42, 8, 5)
    stream = tmp_path / "ontos.stream"
    _emit_gravity_stream(stream, 42, 8, [(6, order[0], 2), (36, order[0], 1)], 40)
    data = bytearray(stream.read_bytes())
    sizes = {1: 9, 2: 9, 3: 17, 4: 10, 5: 34, 6: 55, 7: 57, 8: 73, 9: 57}
    off = 20
    flipped = False
    while off < len(data):
        tag = data[off]
        if tag == 9 and not flipped:
            data[off + 17] ^= 0x01  # low byte of mx
            flipped = True
            break
        off += sizes[tag]
    assert flipped
    corrupt = tmp_path / "corrupt.stream"
    corrupt.write_bytes(bytes(data))
    summary = verify_stream_gravity(corrupt, 42)
    assert summary["mismatch_count"] > 0
    assert not check_reference_match_gravity(summary).passed


def test_engine_diagnose_multipole_run(tmp_path):
    import shutil

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "multipole", run)
    engine = select_engine(run)
    assert engine.name == "ontos"
    ctx = engine.load_context(run, selection="default")
    results = run_checks(ctx)
    names = {r.name for r in results}
    assert "ontos_multipole_match" in names
    assert "ontos_reconstruction_error" in names
    assert all(r.passed for r in results if r.name.startswith("ontos_"))
