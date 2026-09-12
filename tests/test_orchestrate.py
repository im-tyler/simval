"""Orchestrator tests: ontos grid runs, tamper detection, tabulate/outliers, CLI."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from simval.cli import main
from simval.orchestrate import outliers, run_grid, tabulate, verify_run

ONTOS_REPO = Path.home() / "Documents" / "Code Projects" / "ontos"
ONTOS_BIN = ONTOS_REPO / "target" / "release" / "ontos"


def _ensure_bin() -> Path | None:
    env = os.environ.get("ONTOS_BIN")
    if env and Path(env).exists():
        return Path(env)
    if ONTOS_BIN.exists():
        return ONTOS_BIN
    if shutil.which("cargo") is None or not (ONTOS_REPO / "Cargo.toml").exists():
        return None
    subprocess.run(
        ["cargo", "build", "--release", "--quiet", "--manifest-path", str(ONTOS_REPO / "Cargo.toml")],
        capture_output=True,
        text=True,
    )
    return ONTOS_BIN if ONTOS_BIN.exists() else None


BIN = _ensure_bin()
requires_bin = pytest.mark.skipif(BIN is None, reason="ontos binary unavailable and cargo build failed")

GRID = [
    {"name": "all_fine", "mode": "gravity", "ticks": 40, "seed": 42, "bodies": 8},
    {"name": "window", "mode": "gravity", "ticks": 50, "seed": 42, "bodies": 8,
     "events": [["demote-at", 20, 0, 0], ["promote-at", 40, 0, 0]]},
    {"name": "observer", "mode": "gravity", "ticks": 60, "seed": 5, "bodies": 8,
     "observer": 777},
    {"name": "collapse", "mode": "gravity", "ticks": 40, "seed": 42, "bodies": 8,
     "events": [["collapse-at", 6, 0, 0], ["expand-at", 36, 0, 0]]},
    {"name": "radial", "mode": "gravity", "ticks": 40, "seed": 42, "bodies": 8, "radial": True,
     "events": [["collapse-at", 6, 0, 0], ["expand-at", 36, 0, 0]]},
    {"name": "restitution", "mode": "gravity", "ticks": 40, "seed": 11, "bodies": 16,
     "contacts": True, "restitution": 0.5, "friction": 0.25},
    {"name": "walls", "mode": "gravity", "ticks": 40, "seed": 22, "bodies": 8,
     "walls": True},
]


@requires_bin
def test_grid_verifies_clean(tmp_path):
    results = run_grid(GRID, ontos_bin=BIN, workdir=tmp_path)
    assert [r["run"] for r in results] == [s["name"] for s in GRID]
    for r, spec in zip(results, GRID):
        assert "_error" not in r, r
        assert r["mismatch_count"] == 0
        assert r["checks_failed"] == 0
        assert r["ticks_verified"] == spec["ticks"]
        assert r["wall_s"] > 0
        assert (tmp_path / spec["name"] / "ontos.stream").exists()
        meta = json.loads((tmp_path / spec["name"] / "ontos.json").read_text())
        assert meta["seed"] == spec["seed"]
    collapse = results[3]
    assert collapse["collapse_events"] == 1
    assert collapse["expand_events"] == 1
    radial = results[4]
    assert radial["radial_events"] == 1
    assert radial["radial_worst"] < 1e-9
    restitution = results[5]
    assert restitution["contact_events"] >= 1
    walls = results[6]
    assert walls["contact_events"] >= 0


@requires_bin
def test_tampered_stream_reports_mismatch(tmp_path):
    results = run_grid(GRID[:2], ontos_bin=BIN, workdir=tmp_path)
    assert all(r["mismatch_count"] == 0 for r in results)
    stream = tmp_path / "all_fine" / "ontos.stream"
    data = bytearray(stream.read_bytes())
    data[-1] ^= 0x01
    stream.write_bytes(bytes(data))
    row = verify_run(tmp_path / "all_fine")
    assert row["mismatch_count"] > 0
    assert row["checks_failed"] > 0


@requires_bin
def test_cli_smoke(tmp_path, capsys):
    grid = tmp_path / "grid.json"
    grid.write_text(json.dumps(GRID[:2]))
    out = tmp_path / "results.json"
    rc = main(["orchestrate", "--grid", str(grid), "--ontos-bin", str(BIN), "--out", str(out)])
    captured = capsys.readouterr().out
    assert rc == 0
    assert "orchestrate" in captured
    assert "all_fine" in captured and "window" in captured
    assert "outliers" in captured
    saved = json.loads(out.read_text())
    assert len(saved["runs"]) == 2
    assert all(r["mismatch_count"] == 0 for r in saved["runs"])


def _gravity_row(name, **over):
    row = {
        "run": name, "ticks": 100, "mismatch_count": 0,
        "max_position_deviation": 1e-5, "momentum_drift": 1e-3, "energy_drift": 1e-4,
        "post_expansion_deviation": 0.0, "collapse_events": 0, "expand_events": 0,
        "collapse_energy_worst": 0.0, "checks_failed": 0, "wall_s": 1.0,
    }
    row.update(over)
    return row


def test_tabulate_renders_rows_and_missing_metrics():
    table = tabulate([
        _gravity_row("a"),
        _gravity_row("b", momentum_drift=None),
        {"run": "c", "_error": "boom"},
    ])
    lines = table.splitlines()
    assert "a" in lines[1] and "1e-05" in lines[1]
    assert "-" in lines[2].split()
    assert "ERROR: boom" in lines[3]
    assert table.endswith("\n")


def test_outliers_flags_mad_deviation():
    rows = [
        _gravity_row("a"),
        _gravity_row("b"),
        _gravity_row("c"),
        _gravity_row("d", momentum_drift=1e-1),
    ]
    flags = outliers(rows, k=3.0)
    assert [(f["run"], f["metric"]) for f in flags] == [("d", "momentum_drift")]
    assert flags[0]["median"] == 1e-3

    assert outliers(rows[:3], k=3.0) == []

    spread = [_gravity_row("a"), _gravity_row("b", momentum_drift=1.2e-3),
              _gravity_row("c", momentum_drift=0.8e-3), _gravity_row("d", momentum_drift=1.1e-3),
              _gravity_row("e", momentum_drift=1e-1)]
    flagged = outliers(spread, k=3.0)
    assert [(f["run"], f["metric"]) for f in flagged] == [("e", "momentum_drift")]
    assert flagged[0]["mad"] > 0


def test_outliers_ignores_error_rows():
    rows = [_gravity_row("a"), _gravity_row("b"), {"run": "c", "_error": "boom"}]
    assert outliers(rows) == []


def test_outliers_needs_population():
    assert outliers([_gravity_row("a")]) == []


# --- ONT-001: the orchestrator persists every CLI-affecting field ---


def test_ontos_json_persists_full_contract():
    from simval.orchestrate import _ontos_json, normalize_spec

    spec = normalize_spec(
        {
            "name": "full",
            "mode": "gravity",
            "ticks": 40,
            "seed": 11,
            "bodies": 16,
            "events": [["collapse-at", 6, 1, 1], ["expand-at", 30, 1, 1]],
            "observer": 777,
            "contacts": True,
            "radial": True,
            "restitution": 0.5,
            "friction": 0.25,
        }
    )
    meta = _ontos_json(spec)
    assert meta["mode"] == "gravity"
    assert meta["seed"] == 11 and meta["ticks"] == 40 and meta["bodies"] == 16
    assert meta["events"] == [[6, 1, 1, 2], [30, 1, 1, 1]]
    assert meta["observer"] == 777
    assert meta["contacts"] is True and meta["radial"] is True
    assert meta["shells"] is False and meta["walls"] is False
    assert meta["multipole"] is True
    assert meta["restitution"] == 0.5 and meta["friction"] == 0.25
    # round-trips through the gravity contract parser
    from simval.ontos_gravity import GravityContract

    contract = GravityContract.from_metadata(meta)
    assert contract.body_count == 16 and contract.ticks == 40
    assert contract.events == ((6, 3, 2), (30, 3, 1))


def test_ontos_json_life_events_persisted():
    from simval.orchestrate import _ontos_json, normalize_spec

    spec = normalize_spec({"name": "l", "mode": "life", "events": [["demote", 1, 0]]})
    meta = _ontos_json(spec)
    assert meta["mode"] == "life"
    assert meta["events"] == [["demote", 1, 0]]
