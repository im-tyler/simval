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
