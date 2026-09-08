"""Ontos engine adapter: run-dir detection + context wiring.

The reference implementations and stream verifiers live in simval.ontos
(life, version 1) and simval.ontos_gravity (gravity, version 2) — both
stdlib-only; this module holds the EngineAdapter plumbing so the
verifiers stay importable without numpy.
"""
from __future__ import annotations

import json
import struct
from pathlib import Path

from simval.context import EngineAdapter, RunContext, register_engine
from simval.ontos import verify_stream
from simval.ontos_gravity import verify_stream_gravity


def _is_gravity(run: Path) -> bool:
    with (run / "ontos.stream").open("rb") as f:
        header = f.read(8)
    if len(header) < 8 or header[:4] != b"ONTO":
        return False
    return struct.unpack("<I", header[4:8])[0] == 2


class OntosEngine(EngineAdapter):
    name = "ontos"

    def detect(self, run: Path) -> bool:
        return (run / "ontos.stream").exists() and (run / "ontos.json").exists()

    def load_context(self, run: Path, selection: str) -> RunContext:
        meta = json.loads((run / "ontos.json").read_text())
        if "seed" not in meta:
            raise ValueError("ontos.json must contain an integer 'seed'")
        seed = int(meta["seed"])
        ctx = RunContext(run_dir=run, engine=self.name, selection=selection)
        if _is_gravity(run):
            from simval.ontos_gravity import (
                check_collapse_energy,
                check_contact_resolution,
                check_multipole_match,
                check_radial_shape,
                check_reconstruction_error,
                check_zoom_policy,
                parse_stream_v2,
                verify_stream_gravity,
            )

            summary = verify_stream_gravity(run / "ontos.stream", seed)
            extra_checks = []
            if summary.get("collapse_events", 0) or summary.get("expand_events", 0):
                extra_checks.append(check_reconstruction_error(summary))
                extra_checks.append(check_collapse_energy(summary))
                if summary.get("multipole_events", 0):
                    extra_checks.append(check_multipole_match(summary))
                if summary.get("radial_events", 0):
                    extra_checks.append(check_radial_shape(summary))
            if summary.get("contact_run", False):
                extra_checks.append(check_contact_resolution(summary))
            observer = meta.get("observer")
            if observer is not None:
                _, records = parse_stream_v2(run / "ontos.stream")
                cli_events = [
                    (int(t), ry * 2 + rx, int(lv)) for t, rx, ry, lv in meta.get("events", [])
                ]
                extra_checks.append(
                    check_zoom_policy(records, seed, int(observer), cli_events=cli_events)
                )
            if (run / "ontos.wav").exists():
                from simval.ontos_audio import synthesize_stream, wav_bytes

                pcm, digest = synthesize_stream(run / "ontos.stream")
                recorded = (run / "ontos.wav").read_bytes()
                extra_checks.append(_check_audio_match(recorded, wav_bytes(pcm), digest))
            try:
                from simval.ontos_gravity import check_rebound_anchor

                header, records = parse_stream_v2(run / "ontos.stream")
                has_level_events = any(r[0] == "level" for r in records)
                if not has_level_events and not summary.get("contact_run", False):
                    extra_checks.append(
                        check_rebound_anchor(records, seed, header[2], ticks=summary["ticks_verified"])
                    )
            except ImportError:
                pass
            ctx.extra = {"ontos_gravity_summary": summary, "ontos_extra_checks": extra_checks}
            ctx.run_params = {
                "engine": self.name,
                "mode": "gravity",
                "seed": seed,
                "domain": "nbody-multiscale",
                "ticks": summary["ticks_verified"],
                **({"observer": int(observer)} if observer is not None else {}),
            }
        else:
            summary = verify_stream(run / "ontos.stream", seed)
            ctx.extra = {"ontos_summary": summary}
            ctx.run_params = {
                "engine": self.name,
                "mode": "life",
                "seed": seed,
                "domain": "discrete-multiscale",
                "ticks": summary["ticks_verified"],
            }
        return ctx


def _check_audio_match(recorded: bytes, reference: bytes, digest: int):
    from simval.result import DiagnosticResult

    ok = recorded == reference
    return DiagnosticResult(
        name="ontos_audio_match",
        passed=ok,
        threshold=0.0,
        value=0.0 if ok else 1.0,
        detail={
            "audio_hash": f"{digest:016x}",
            "recorded_bytes": len(recorded),
            "reference_bytes": len(reference),
        },
    )


register_engine(OntosEngine())
