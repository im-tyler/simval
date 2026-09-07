"""Ontos adapter tests: independent reference vs recorded streams."""
from __future__ import annotations

import struct
from pathlib import Path

import pytest

from simval.context import select_engine
from simval.ontos import (
    FNV_OFFSET_BASIS,
    ReferenceWorld,
    check_reference_match,
    check_tick_monotonicity,
    fnv1a64,
    parse_stream,
    verify_stream,
)
from simval.ontos_eng import OntosEngine
from simval.pipeline import run_checks

EXAMPLES = Path(__file__).parent.parent / "examples" / "ontos"
R_PENTOMINO = EXAMPLES / "r_pentomino"
ALL_FINE = EXAMPLES / "all_fine"


def test_fnv_known_values():
    assert fnv1a64(b"") == FNV_OFFSET_BASIS
    assert fnv1a64(b"") == 0xCBF29CE484222325
    assert fnv1a64(b"a") == 0xAF63DC4C8601EC8C


@pytest.mark.parametrize(
    "run_dir,seed",
    [(R_PENTOMINO, 42), (ALL_FINE, 7)],
)
def test_reference_matches_stream(run_dir, seed):
    summary = verify_stream(run_dir / "ontos.stream", seed)
    assert summary["mismatch_count"] == 0
    assert summary["tick_monotonic"]
    assert summary["ticks_verified"] == 64
    assert summary["records_compared"] == 320


def test_corrupted_hash_fails(tmp_path):
    data = bytearray((R_PENTOMINO / "ontos.stream").read_bytes())
    header, records = parse_stream(R_PENTOMINO / "ontos.stream")
    first_state = next(i for i, r in enumerate(records) if r[0] == "state")
    offset = 16
    for record in records:
        size = {"tick": 9, "snapshot": 9, "flip": 17, "level": 10, "state": 34}[record[0]]
        if record[0] == "state" and records.index(record) == first_state:
            data[offset + size - 1] ^= 0xFF
            break
        offset += size
    corrupt = tmp_path / "ontos.stream"
    corrupt.write_bytes(bytes(data))
    summary = verify_stream(corrupt, 42)
    assert summary["mismatch_count"] > 0
    result = check_reference_match(summary)
    assert not result.passed


def test_parser_rejects_bad_magic(tmp_path):
    bad = tmp_path / "ontos.stream"
    bad.write_bytes(b"NOPE" + b"\x00" * 12)
    with pytest.raises(ValueError, match="bad magic"):
        parse_stream(bad)


def test_parser_rejects_truncation(tmp_path):
    data = (R_PENTOMINO / "ontos.stream").read_bytes()
    truncated = tmp_path / "ontos.stream"
    truncated.write_bytes(data[:-4])
    with pytest.raises((ValueError, struct.error)):
        parse_stream(truncated)


def test_engine_detect_and_diagnose(tmp_path):
    import shutil

    run = tmp_path / "ontos_run"
    shutil.copytree(R_PENTOMINO, run)
    engine = select_engine(run)
    assert isinstance(engine, OntosEngine)
    assert engine.name == "ontos"
    ctx = engine.load_context(run, selection="default")
    results = run_checks(ctx)
    names = {r.name for r in results}
    assert "ontos_reference_match" in names
    assert "ontos_tick_monotonicity" in names
    assert all(r.passed for r in results if r.name.startswith("ontos_"))


def test_wrong_seed_fails_on_promote_fixture(tmp_path):
    import shutil

    run = tmp_path / "ontos_run"
    shutil.copytree(EXAMPLES / "promote_roundtrip", run)
    summary_seeded = verify_stream(run / "ontos.stream", 42)
    assert summary_seeded["mismatch_count"] == 0
    summary_wrong = verify_stream(run / "ontos.stream", 43)
    assert summary_wrong["mismatch_count"] > 0
    assert not check_reference_match(summary_wrong).passed


def _emit_stream(path, world, schedule, ticks):
    """Serialize a reference run to stream bytes per spec section 9."""
    out = bytearray(b"ONTO")
    out += struct.pack("<III", 1, 128, 128)
    for rx, ry, level in schedule:
        world.set_level(rx, ry, "fine" if level else "coarse")
        out += b"\x04" + struct.pack("<IIB", rx, ry, level)
    for _ in range(ticks):
        world.step()
        out += b"\x01" + struct.pack("<Q", world.tick)
        out += b"\x02" + struct.pack("<Q", world.population())
        for ry in (0, 1):
            for rx in (0, 1):
                region = world.regions[world.region_index(rx, ry)]
                out += b"\x05" + struct.pack(
                    "<QIIBQQ",
                    world.tick,
                    rx,
                    ry,
                    1 if region.level == "fine" else 0,
                    region.population(),
                    region.hash(),
                )
    Path(path).write_bytes(bytes(out))


def test_randomized_schedules_self_consistent(tmp_path):
    import random

    rng = random.Random(20260906)
    for trial in range(12):
        seed = rng.randrange(2**64)
        ops = rng.randrange(0, 5)
        schedule = [
            (rng.randrange(2), rng.randrange(2), rng.randrange(2)) for _ in range(ops)
        ]
        ticks = rng.randrange(1, 40)
        world = ReferenceWorld(seed=seed)
        world.seed_r_pentomino()
        stream = tmp_path / f"case_{trial}.stream"
        _emit_stream(stream, world, schedule, ticks)
        summary = verify_stream(stream, seed)
        assert summary["mismatch_count"] == 0, (trial, schedule, summary["mismatches"])
        assert summary["tick_monotonic"] is True
        assert summary["ticks_verified"] == ticks


def test_module_cli_verifies_and_rejects(tmp_path, capsys):
    from simval.ontos import _main

    assert _main([str(R_PENTOMINO / "ontos.stream"), "42"]) == 0
    out = capsys.readouterr().out
    assert "OK" in out and "mismatches=0" in out
    data = bytearray((R_PENTOMINO / "ontos.stream").read_bytes())
    data[-1] ^= 0xFF
    corrupt = tmp_path / "corrupt.stream"
    corrupt.write_bytes(bytes(data))
    assert _main([str(corrupt), "42"]) == 1
    assert _main([str(tmp_path / "missing.stream"), "42"]) == 2
