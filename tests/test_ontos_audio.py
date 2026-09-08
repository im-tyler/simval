"""Spec section 22 modal audio reference tests."""
from __future__ import annotations

import struct
from pathlib import Path

from simval.ontos_audio import (
    AUDIO_SR,
    RING,
    TAIL_BLOCKS,
    audio_hash,
    collect_excitations,
    synthesize,
    synthesize_stream,
    wav_bytes,
)
from simval.ontos_gravity import parse_stream_v2

CONTACT_EXAMPLES = Path(__file__).parent.parent / "examples" / "ontos_contact"


def test_silence_is_zero_pcm():
    pcm = synthesize([], 3)
    assert len(pcm) == (3 + TAIL_BLOCKS) * 64 * 2
    assert pcm == bytes(len(pcm))
    assert audio_hash(pcm) == audio_hash(bytes(len(pcm)))


def test_known_excitation_pins_hash():
    mu_a = (1.25 * 0.75) / (1.25 + 0.75)
    mu_b = (2.0 * 1.5) / (2.0 + 1.5)
    pcm = synthesize([(5, mu_a, 0.3), (40, mu_b, 0.05)], 100)
    assert audio_hash(pcm) == 0xAF22AA8908656DBD
    assert pcm == synthesize([(5, mu_a, 0.3), (40, mu_b, 0.05)], 100)


def test_ring_decays_to_silence():
    pcm = synthesize([(0, (1.0 * 1.0) / (1.0 + 1.0), 0.8)], 300)
    peak = max(abs(struct.unpack_from("<h", pcm, i)[0]) for i in range(0, len(pcm), 2))
    assert peak > 8000
    start = (64 + RING) * 2
    tail = struct.unpack_from("<64h", pcm, start)
    assert all(s == 0 for s in tail)


def test_wav_container_layout():
    wav = wav_bytes(struct.pack("<4h", 0, 1, -1, 32767))
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert wav[12:16] == b"fmt "
    assert wav[36:40] == b"data"
    assert struct.unpack_from("<I", wav, 4)[0] == 44
    assert struct.unpack_from("<I", wav, 40)[0] == 8
    assert struct.unpack_from("<I", wav, 24)[0] == AUDIO_SR
    assert len(wav) == 52


def test_reference_matches_recorded_wav():
    pcm, digest = synthesize_stream(CONTACT_EXAMPLES / "contact" / "ontos.stream")
    recorded = (CONTACT_EXAMPLES / "contact" / "ontos.wav").read_bytes()
    assert wav_bytes(pcm) == recorded
    assert digest == 0xEE83454527DBE43B


def test_reference_matches_composition_wav():
    pcm, digest = synthesize_stream(
        CONTACT_EXAMPLES / "contact_collapse" / "ontos.stream"
    )
    recorded = (CONTACT_EXAMPLES / "contact_collapse" / "ontos.wav").read_bytes()
    assert wav_bytes(pcm) == recorded
    assert digest == 0x85B6B183008818DF


def test_excitations_use_tick_body_masses():
    _, records = parse_stream_v2(CONTACT_EXAMPLES / "contact" / "ontos.stream")
    excitations, final_tick = collect_excitations(records)
    assert final_tick == 400
    assert len(excitations) == 5
    first = excitations[0]
    assert first[0] == 1
    assert first[1] > 0.0 and first[2] > 0.0


def test_cli_expect_mismatch_fails(tmp_path):
    from simval.ontos_audio import _main

    stream = CONTACT_EXAMPLES / "contact" / "ontos.stream"
    assert _main([str(stream), "--expect", "0" * 16]) == 1
    assert _main([str(stream), "--wav", str(tmp_path / "a.wav")]) == 0
    assert (tmp_path / "a.wav").read_bytes() == (
        CONTACT_EXAMPLES / "contact" / "ontos.wav"
    ).read_bytes()


def test_walls_example_wav_matches():
    # Includes two collapsed-region monopole contacts: the pseudo-id mu
    # rule (reduced mass vs the RegionCollapsed mass) must hold for the
    # resynthesis to stay bit-identical.
    pcm, digest = synthesize_stream(CONTACT_EXAMPLES / "walls" / "ontos.stream")
    recorded = (CONTACT_EXAMPLES / "walls" / "ontos.wav").read_bytes()
    assert wav_bytes(pcm) == recorded
    assert digest == 0x70A1D0539170B265


def test_restitution_example_wav_matches():
    pcm, digest = synthesize_stream(CONTACT_EXAMPLES / "restitution" / "ontos.stream")
    recorded = (CONTACT_EXAMPLES / "restitution" / "ontos.wav").read_bytes()
    assert wav_bytes(pcm) == recorded
    assert digest == 0xC4317E51BCE80E83


def test_monopole_mu_uses_collapse_mass():
    from simval.ontos_gravity import MONOPOLE_BASE, parse_stream_v2

    _, records = parse_stream_v2(CONTACT_EXAMPLES / "walls" / "ontos.stream")
    excitations, _ = collect_excitations(records)
    masses = {}
    collapse_mass = {}
    contacts = []
    for record in records:
        if record[0] == "body":
            masses[record[2]] = record[9]
        elif record[0] == "collapsed":
            collapse_mass[record[3] * 2 + record[2]] = record[5]
        elif record[0] == "contact":
            contacts.append(record)
    want = []
    for record in contacts:
        _, tick, a, b, jn, _cx, _cy = record
        ma = masses[a]
        if b >= MONOPOLE_BASE:
            m = collapse_mass[b - MONOPOLE_BASE]
            mu = (ma * m) / (ma + m)
        else:
            mu = (ma * masses[b]) / (ma + masses[b])
        want.append((tick, mu, jn))
    assert any(r[3] >= MONOPOLE_BASE for r in contacts)
    assert excitations == want
