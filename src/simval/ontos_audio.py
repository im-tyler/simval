"""Ontos modal audio reference: independent spec section 22 synthesizer.

Re-synthesizes the WAV for an ontos stream strictly from the spec text
(sections 21-22): Contact records excite damped second-order resonators,
mixed in stream order into one f64 buffer, quantized to mono PCM16, and
hashed with FNV-1a64. Pure stdlib; float ops stay in the +,-,*,/ closure
with fixed order, so this reference is bit-compatible with the Rust CLI's
`--wav` output and the C++ consumers.
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
from pathlib import Path

from simval.ontos import fnv1a64
from simval.ontos_gravity import parse_stream_v2

AUDIO_SR = 65536
SAMPLES_PER_TICK = 64
RING = 16384
TAIL_BLOCKS = 260
OMEGA0 = 0.0004448824124529259
PARTIAL = (1.0, 4.0, 9.0)
RHO = (0.9990, 0.9985, 0.9980)
AMP = (0.5, 0.3, 0.2)


def collect_excitations(records):
    """Stream-order (tick, mu, jn) excitations + final tick.

    mu follows spec section 22 with the section 24 amendment: body pairs
    use the reduced mass of the two bodies; wall pseudo ids (>=
    0xFFFFFF00) are infinitely massive (mu = m_a); collapsed-region
    monopole pseudo ids (>= 0xFF000000) use the reduced mass against
    the region's RegionCollapsed mass **at contact time** — captured in
    one stream-order pass, so a recollapse that changes the region mass
    does not retroactively rewrite earlier excitations. Body masses are
    immutable per body and a tick's Contact records precede that tick's
    BodyState block, so those resolve after the pass; only the collapse
    mass timeline is event-order-sensitive.
    """
    masses = {}
    collapse_mass = {}
    pending = []  # (tick, body_a, body_b, jn, mono_mass_at_contact_or_None)
    last_tick = 0
    for record in records:
        kind = record[0]
        if kind == "body":
            _, _tick, bid, _region, _level, _x, _y, _vx, _vy, mass = record
            masses[bid] = mass
        elif kind == "collapsed":
            _, _tick, rx, ry, _count, mass, _com_x, _com_y, _px, _py, _energy = record
            collapse_mass[ry * 2 + rx] = mass
        elif kind == "contact":
            _, tick, body_a, body_b, jn, _cx, _cy = record
            if body_b >= 0xFFFFFF00:
                pending.append((tick, body_a, body_b, jn, None))
            elif body_b >= 0xFF000000:
                region = body_b - 0xFF000000
                if region not in collapse_mass:
                    raise ValueError(
                        f"monopole contact at tick {tick} references region {region} "
                        "with no preceding RegionCollapsed record"
                    )
                pending.append((tick, body_a, body_b, jn, collapse_mass[region]))
            else:
                pending.append((tick, body_a, body_b, jn, None))
        elif kind == "tick":
            last_tick = record[1]
    excitations = []
    for tick, body_a, body_b, jn, mono_m in pending:
        ma = masses[body_a]
        if body_b >= 0xFFFFFF00:
            mu = ma
        elif mono_m is not None:
            mu = (ma * mono_m) / (ma + mono_m)
        else:
            mu = (ma * masses[body_b]) / (ma + masses[body_b])
        excitations.append((tick, mu, jn))
    return excitations, last_tick


def synthesize(excitations, final_tick):
    """Spec section 22: (pcm bytes, fnv hash, sample count)."""
    n = (final_tick + TAIL_BLOCKS) * SAMPLES_PER_TICK
    buf = [0.0] * n
    for tick, mu, jn in excitations:
        e = (tick + 1) * SAMPLES_PER_TICK
        for k in range(3):
            omega = OMEGA0 * PARTIAL[k] / mu
            a = (2.0 - omega) * RHO[k]
            b = RHO[k] * RHO[k]
            s0 = AMP[k] * jn
            s_prev = s0
            s_prev2 = 0.0
            for i in range(RING):
                if i == 0:
                    s = s0
                elif i == 1:
                    s = a * s0
                else:
                    s = a * s_prev - b * s_prev2
                buf[e + i] += s
                s_prev2 = s_prev
                s_prev = s
    pcm = bytearray(n * 2)
    for idx in range(n):
        v = buf[idx]
        if v < -1.0:
            v = -1.0
        elif v > 1.0:
            v = 1.0
        sample = math.floor(v * 32767.0 + 0.5)
        struct.pack_into("<h", pcm, idx * 2, sample)
    return bytes(pcm)


def wav_bytes(pcm):
    data_size = len(pcm)
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, AUDIO_SR, AUDIO_SR * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
        + pcm
    )


def audio_hash(pcm):
    return fnv1a64(pcm)


def synthesize_stream(path):
    (_, _, _), records = parse_stream_v2(path)
    excitations, final_tick = collect_excitations(records)
    pcm = synthesize(excitations, final_tick)
    return pcm, audio_hash(pcm)


def _main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m simval.ontos_audio",
        description="Synthesize the spec section 22 modal audio for an ontos stream",
    )
    parser.add_argument("stream", help="path to a v2 .stream file")
    parser.add_argument("--wav", help="write the synthesized WAV here")
    parser.add_argument("--expect", help="expected 16-hex-digit FNV audio hash")
    args = parser.parse_args(argv)
    try:
        pcm, digest = synthesize_stream(args.stream)
    except (FileNotFoundError, ValueError) as e:
        print(f"simval.ontos_audio: error: {e}", file=sys.stderr)
        return 2
    if args.wav:
        Path(args.wav).write_bytes(wav_bytes(pcm))
    ok = args.expect is None or args.expect.lower() == f"{digest:016x}"
    print(
        f"ontos audio: samples={len(pcm) // 2} hash={digest:016x}"
        + ("" if args.expect is None else f" expect={args.expect.lower()} {'OK' if ok else 'MISMATCH'}")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
