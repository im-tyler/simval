"""Ontos gravity adapter tests: independent spec reimplementation vs recorded streams."""
from __future__ import annotations

from pathlib import Path

import pytest

from simval.context import select_engine
from simval.ontos_gravity import (
    SplitMix64,
    check_bounded_drift,
    check_reference_match_gravity,
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
