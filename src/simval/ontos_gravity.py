"""Ontos gravity reference: independent version-2 stream verifier.

Implements the gravity epoch of the ontos stream spec (ontos
docs/STREAM_SPEC.md Part II) strictly from the spec text and verifies
recorded streams against this reimplementation. Pure stdlib. Float ops
stay in the spec closure (+ - * / sqrt) with fixed order, so this
reference is bit-compatible with the Rust simulator.
"""
from __future__ import annotations

import math
import struct
import sys
from pathlib import Path

from simval.ontos import MAGIC, fnv1a64, parse_stream
from simval.result import DiagnosticResult

G = 1.0
EPS2 = 1.0
DT = 1.0 / 1024.0
WINDOW = 32
DEGREE = 8
SAMPLES = 33
UNMANAGED = 255
TWO_POW_NEG64 = 2.0**-64


class SplitMix64:
    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFFFFFFFFFF

    def next(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)


def initial_conditions(seed: int, count: int) -> list:
    rng = SplitMix64(seed)
    bodies = []
    for i in range(count):
        u0 = rng.next()
        u1 = rng.next()
        u2 = rng.next()
        u3 = rng.next()
        u4 = rng.next()
        bodies.append(
            {
                "id": i,
                "mass": 0.5 + u0 * TWO_POW_NEG64 * 2.0,
                "x": 32.0 + u1 * TWO_POW_NEG64 * 64.0,
                "y": 32.0 + u2 * TWO_POW_NEG64 * 64.0,
                "vx": (u3 * TWO_POW_NEG64 - 0.5) * 0.5,
                "vy": (u4 * TWO_POW_NEG64 - 0.5) * 0.5,
            }
        )
    return bodies


def region_at(x: float, y: float) -> int:
    if x < 0.0 or x >= 128.0 or y < 0.0 or y >= 128.0:
        return UNMANAGED
    rx = int(x / 64.0)
    ry = int(y / 64.0)
    return ry * 2 + rx


def clenshaw(c, s: float) -> float:
    b1 = 0.0
    b2 = 0.0
    for j in range(DEGREE, 0, -1):
        b0 = c[j] + 2.0 * s * b1 - b2
        b2 = b1
        b1 = b0
    return c[0] + s * b1 - b2


def cheb_table():
    t = [[0.0] * SAMPLES for _ in range(DEGREE + 1)]
    w = [1.0] * SAMPLES
    w[0] = 0.5
    w[SAMPLES - 1] = 0.5
    for k in range(SAMPLES):
        s = -1.0 + k / 16.0
        t[0][k] = 1.0
        t[1][k] = s
        for j in range(2, DEGREE + 1):
            t[j][k] = 2.0 * s * t[j - 1][k] - t[j - 2][k]
    return t, w


CHEB_T, CHEB_W = cheb_table()


def project(ys):
    g = [[0.0] * (DEGREE + 1) for _ in range(DEGREE + 1)]
    for j in range(DEGREE + 1):
        for l in range(DEGREE + 1):
            total = 0.0
            for k in range(SAMPLES):
                total += CHEB_W[k] * CHEB_T[j][k] * CHEB_T[l][k]
            g[j][l] = total
    b = [0.0] * (DEGREE + 1)
    for j in range(DEGREE + 1):
        total = 0.0
        for k in range(SAMPLES):
            total += CHEB_W[k] * ys[k] * CHEB_T[j][k]
        b[j] = total
    return cholesky_solve(g, b)


def cholesky_solve(g, b):
    n = DEGREE + 1
    l = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            total = g[i][j]
            for k in range(j):
                total -= l[i][k] * l[j][k]
            if i == j:
                l[i][j] = math.sqrt(total)
            else:
                l[i][j] = total / l[j][j]
    z = [0.0] * n
    for i in range(n):
        total = b[i]
        for k in range(i):
            total -= l[i][k] * z[k]
        z[i] = total / l[i][i]
    c = [0.0] * n
    for i in range(n - 1, -1, -1):
        total = z[i]
        for k in range(i + 1, n):
            total -= l[k][i] * c[k]
        c[i] = total / l[i][i]
    return c


class GravityWorld:
    def __init__(self, seed: int, count: int) -> None:
        self.bodies = initial_conditions(seed, count)
        self.coarse = [None] * count
        self.body_region = [UNMANAGED] * count
        self.region_coarse = [False] * 4
        self.events: dict[int, list[tuple[int, bool]]] = {}
        self.tick = 0
        px = 0.0
        py = 0.0
        for b in self.bodies:
            px += b["mass"] * b["vx"]
            py += b["mass"] * b["vy"]
        self.px = px
        self.py = py

    def schedule(self, tick: int, region: int, to_coarse: bool) -> None:
        self.events.setdefault(tick, []).append((region, to_coarse))

    def _state_at(self, i: int, t: int) -> dict:
        b = dict(self.bodies[i])
        fit = self.coarse[i]
        if fit is not None:
            s = -1.0 + (t - fit["t0"]) / 32.0
            b["x"] = clenshaw(fit["c"][0], s)
            b["y"] = clenshaw(fit["c"][1], s)
            b["vx"] = clenshaw(fit["c"][2], s)
            b["vy"] = clenshaw(fit["c"][3], s)
        return b

    def _leapfrog(self, bodies):
        half = DT * 0.5
        ax, ay = self._accumulate(bodies)
        for i, b in enumerate(bodies):
            b["vx"] += ax[i] * half
            b["vy"] += ay[i] * half
        for b in bodies:
            b["x"] += b["vx"] * DT
            b["y"] += b["vy"] * DT
        ax, ay = self._accumulate(bodies)
        for i, b in enumerate(bodies):
            b["vx"] += ax[i] * half
            b["vy"] += ay[i] * half

    @staticmethod
    def _accumulate(bodies):
        n = len(bodies)
        ax = [0.0] * n
        ay = [0.0] * n
        for i in range(n):
            for j in range(i + 1, n):
                dx = bodies[j]["x"] - bodies[i]["x"]
                dy = bodies[j]["y"] - bodies[i]["y"]
                s2 = dx * dx + dy * dy + EPS2
                inv3 = 1.0 / (s2 * math.sqrt(s2))
                fx = G * inv3 * dx
                fy = G * inv3 * dy
                ax[i] += bodies[j]["mass"] * fx
                ay[i] += bodies[j]["mass"] * fy
                ax[j] -= bodies[i]["mass"] * fx
                ay[j] -= bodies[i]["mass"] * fy
        return ax, ay

    def _pre_integrate(self, bodies):
        samples = [[dict(b) for _ in range(SAMPLES)] for b in bodies]
        cur = [dict(b) for b in bodies]
        for k in range(1, SAMPLES):
            self._leapfrog(cur)
            for i, b in enumerate(cur):
                samples[i][k] = dict(b)
        return samples

    def _fit_members(self, members, t0):
        subset = [self._state_at(i, t0) for i in members]
        samples = self._pre_integrate(subset)
        for slot, i in enumerate(members):
            fits = [
                project([s["x"] for s in samples[slot]]),
                project([s["y"] for s in samples[slot]]),
                project([s["vx"] for s in samples[slot]]),
                project([s["vy"] for s in samples[slot]]),
            ]
            self.coarse[i] = {"c": fits, "t0": t0}

    def _demote(self, region: int, t0: int) -> None:
        x0 = (region % 2) * 64.0
        y0 = (region // 2) * 64.0
        members = [
            i
            for i in range(len(self.bodies))
            if (lambda b: b["x"] >= x0 and b["x"] < x0 + 64.0 and b["y"] >= y0 and b["y"] < y0 + 64.0)(
                self._state_at(i, t0)
            )
        ]
        self.region_coarse[region] = True
        if not members:
            return
        self._fit_members(members, t0)
        for i in members:
            self.body_region[i] = region

    def _promote(self, region: int, t: int) -> None:
        for i in range(len(self.bodies)):
            if self.coarse[i] is not None and self.body_region[i] == region:
                self.bodies[i] = self._state_at(i, t)
                self.coarse[i] = None
                self.body_region[i] = UNMANAGED
        self.region_coarse[region] = False

    def _refit(self, region: int, t: int) -> None:
        x0 = (region % 2) * 64.0
        y0 = (region // 2) * 64.0
        members = [
            i for i in range(len(self.bodies)) if self.coarse[i] is not None and self.body_region[i] == region
        ]
        for i in members:
            self.bodies[i] = self._state_at(i, t)
        keep = [
            i
            for i in members
            if self.bodies[i]["x"] >= x0
            and self.bodies[i]["x"] < x0 + 64.0
            and self.bodies[i]["y"] >= y0
            and self.bodies[i]["y"] < y0 + 64.0
        ]
        for i in members:
            if i not in keep:
                self.coarse[i] = None
                self.body_region[i] = UNMANAGED
        if not keep:
            self.region_coarse[region] = False
            return
        self._fit_members(keep, t)
        for i in keep:
            self.body_region[i] = region

    def step(self) -> None:
        entering = self.tick + 1
        for region, to_coarse in self.events.pop(entering, []):
            if to_coarse:
                self._demote(region, entering)
            else:
                self._promote(region, entering)
        for region in range(4):
            if self.region_coarse[region]:
                ended = any(
                    self.body_region[i] == region
                    and self.coarse[i] is not None
                    and entering == self.coarse[i]["t0"] + WINDOW
                    for i in range(len(self.bodies))
                )
                if ended:
                    self._refit(region, entering)

        n = len(self.bodies)
        coarse = [self.coarse[i] is not None for i in range(n)]
        half = DT * 0.5
        view = [self._state_at(i, entering) for i in range(n)]
        ax_ff, ay_ff, ax_fc, ay_fc = accel_split(view, coarse)
        for i in range(n):
            if not coarse[i]:
                self.bodies[i]["vx"] += ax_ff[i] * half
                self.bodies[i]["vy"] += ay_ff[i] * half
        for i in range(n):
            if not coarse[i]:
                self.bodies[i]["vx"] += ax_fc[i] * half
                self.bodies[i]["vy"] += ay_fc[i] * half
                self.px += self.bodies[i]["mass"] * (ax_fc[i] * half)
                self.py += self.bodies[i]["mass"] * (ay_fc[i] * half)
        for i in range(n):
            if not coarse[i]:
                self.bodies[i]["x"] += self.bodies[i]["vx"] * DT
                self.bodies[i]["y"] += self.bodies[i]["vy"] * DT
        view = [self._state_at(i, entering) for i in range(n)]
        ax_ff, ay_ff, ax_fc, ay_fc = accel_split(view, coarse)
        for i in range(n):
            if not coarse[i]:
                self.bodies[i]["vx"] += ax_ff[i] * half
                self.bodies[i]["vy"] += ay_ff[i] * half
        for i in range(n):
            if not coarse[i]:
                self.bodies[i]["vx"] += ax_fc[i] * half
                self.bodies[i]["vy"] += ay_fc[i] * half
                self.px += self.bodies[i]["mass"] * (ax_fc[i] * half)
                self.py += self.bodies[i]["mass"] * (ay_fc[i] * half)
        self.tick = entering

    def totals(self):
        n = len(self.bodies)
        view = [self._state_at(i, self.tick) for i in range(n)]
        fine = 0
        coarse_n = 0
        mass = 0.0
        ke = 0.0
        for b in view:
            if self.coarse[b["id"]] is not None:
                coarse_n += 1
            else:
                fine += 1
            mass += b["mass"]
            ke += 0.5 * b["mass"] * (b["vx"] * b["vx"] + b["vy"] * b["vy"])
        pe = 0.0
        for i in range(n):
            for j in range(i + 1, n):
                dx = view[j]["x"] - view[i]["x"]
                dy = view[j]["y"] - view[i]["y"]
                s2 = dx * dx + dy * dy + EPS2
                pe -= view[i]["mass"] * view[j]["mass"] / math.sqrt(s2)
        return fine, coarse_n, mass, self.px, self.py, ke + pe

    def state_bytes(self, i: int) -> bytes:
        b = self._state_at(i, self.tick)
        level = 0 if self.coarse[i] is not None else 1
        return struct.pack(
            "<IdddddB", b["id"], b["x"], b["y"], b["vx"], b["vy"], b["mass"], level
        )

    def emitted_state(self, i: int):
        b = self._state_at(i, self.tick)
        level = 0 if self.coarse[i] is not None else 1
        region = self.body_region[i] if self.coarse[i] is not None else region_at(b["x"], b["y"])
        return b, region, level

    def region_hash(self, region: int):
        members = []
        for i in range(len(self.bodies)):
            if self.coarse[i] is not None:
                if self.body_region[i] == region:
                    members.append(i)
            else:
                b = self._state_at(i, self.tick)
                if region_at(b["x"], b["y"]) == region:
                    members.append(i)
        level = 0 if self.region_coarse[region] else 1
        payload = bytes([level])
        for i in sorted(members):
            payload += self.state_bytes(i)
        return level, len(members), fnv1a64(payload)

    def world_hash(self) -> int:
        payload = struct.pack("<Q", self.tick)
        for i in range(len(self.bodies)):
            payload += self.state_bytes(i)
        return fnv1a64(payload)


def accel_split(view, coarse):
    n = len(view)
    ax_ff = [0.0] * n
    ay_ff = [0.0] * n
    ax_fc = [0.0] * n
    ay_fc = [0.0] * n
    for i in range(n):
        for j in range(i + 1, n):
            dx = view[j]["x"] - view[i]["x"]
            dy = view[j]["y"] - view[i]["y"]
            s2 = dx * dx + dy * dy + EPS2
            inv3 = 1.0 / (s2 * math.sqrt(s2))
            fx = G * inv3 * dx
            fy = G * inv3 * dy
            ci, cj = coarse[i], coarse[j]
            if not ci and not cj:
                ax_ff[i] += view[j]["mass"] * fx
                ay_ff[i] += view[j]["mass"] * fy
                ax_ff[j] -= view[i]["mass"] * fx
                ay_ff[j] -= view[i]["mass"] * fy
            elif not ci and cj:
                ax_fc[i] += view[j]["mass"] * fx
                ay_fc[i] += view[j]["mass"] * fy
            elif ci and not cj:
                ax_fc[j] -= view[i]["mass"] * fx
                ay_fc[j] -= view[i]["mass"] * fy
    return ax_ff, ay_ff, ax_fc, ay_fc


def parse_stream_v2(path):
    data = Path(path).read_bytes()
    if len(data) < 20 or data[:4] != MAGIC:
        raise ValueError("not an ontos stream: bad magic")
    version = struct.unpack_from("<I", data, 4)[0]
    if version != 2:
        raise ValueError(f"not a gravity stream (version {version})")
    world_w, world_h, body_count = struct.unpack_from("<III", data, 8)
    records = []
    offset = 20
    while offset < len(data):
        tag = data[offset]
        offset += 1
        if tag == 1:
            (tick,) = struct.unpack_from("<Q", data, offset)
            offset += 8
            records.append(("tick", tick))
        elif tag == 2:
            (population,) = struct.unpack_from("<Q", data, offset)
            offset += 8
            records.append(("snapshot", population))
        elif tag == 3:
            tick, x, y = struct.unpack_from("<QII", data, offset)
            offset += 16
            records.append(("flip", tick, x, y))
        elif tag == 4:
            region_x, region_y, level = struct.unpack_from("<IIB", data, offset)
            offset += 9
            records.append(("level", region_x, region_y, level))
        elif tag == 5:
            vals = struct.unpack_from("<QIIBQQ", data, offset)
            offset += 33
            records.append(("state", *vals))
        elif tag == 6:
            vals = struct.unpack_from("<QIBBddddd", data, offset)
            offset += 54
            records.append(("body", *vals))
        elif tag == 7:
            vals = struct.unpack_from("<QQQdddd", data, offset)
            offset += 56
            records.append(("totals", *vals))
        else:
            raise ValueError(f"unknown record tag {tag} at offset {offset - 1}")
    return (world_w, world_h, body_count), records


def verify_stream_gravity(path, seed: int) -> dict:
    (world_w, world_h, body_count), records = parse_stream_v2(path)
    if world_w != 128 or world_h != 128:
        raise ValueError(f"unsupported world size {world_w}x{world_h}")
    world = GravityWorld(seed, body_count)
    reference = GravityWorld(seed, body_count)

    mismatches = []
    compared = 0
    last_tick = 0
    pending = []
    max_pos_dev = 0.0

    for record in records:
        kind = record[0]
        if kind == "level":
            _, rx, ry, level = record
            pending.append((ry * 2 + rx, level == 0))
        elif kind == "tick":
            _, tick = record
            for region, to_coarse in pending:
                world.schedule(world.tick + 1, region, to_coarse)
            pending.clear()
            world.step()
            reference.step()
            last_tick = tick
            if tick != world.tick:
                mismatches.append({"tick": tick, "field": "tick", "expected": tick, "actual": world.tick})
            for i in range(len(world.bodies)):
                b = world._state_at(i, world.tick)
                r = reference.bodies[i]
                dev = max(abs(b["x"] - r["x"]), abs(b["y"] - r["y"]))
                if dev > max_pos_dev:
                    max_pos_dev = dev
        elif kind == "snapshot":
            compared += 1
        elif kind == "totals":
            _, tick, fine, coarse_n, mass, px, py, energy = record
            compared += 1
            w_fine, w_coarse, w_mass, w_px, w_py, w_energy = world.totals()
            if fine != w_fine:
                mismatches.append({"tick": tick, "field": "fine_count", "expected": fine, "actual": w_fine})
            if coarse_n != w_coarse:
                mismatches.append({"tick": tick, "field": "coarse_count", "expected": coarse_n, "actual": w_coarse})
            for name, got, want in (
                ("mass", mass, w_mass),
                ("px", px, w_px),
                ("py", py, w_py),
                ("energy", energy, w_energy),
            ):
                if struct.pack("<d", got) != struct.pack("<d", want):
                    mismatches.append({"tick": tick, "field": name, "expected": got, "actual": want})
        elif kind == "state":
            _, tick, rx, ry, level, population, rhash = record
            compared += 1
            w_level, w_pop, w_hash = world.region_hash(ry * 2 + rx)
            if (level, population) != (w_level, w_pop) or rhash != w_hash:
                mismatches.append(
                    {
                        "tick": tick,
                        "field": "region_state",
                        "expected": (level, population, rhash),
                        "actual": (w_level, w_pop, w_hash),
                    }
                )
        elif kind == "body":
            _, tick, bid, region, level, x, y, vx, vy, mass = record
            compared += 1
            b, w_region, w_level = world.emitted_state(bid)
            ok = (
                region == w_region
                and level == w_level
                and struct.pack("<ddddd", x, y, vx, vy, mass)
                == struct.pack("<ddddd", b["x"], b["y"], b["vx"], b["vy"], b["mass"])
            )
            if not ok:
                mismatches.append(
                    {
                        "tick": tick,
                        "field": f"body_{bid}",
                        "expected": (region, level, x, y, vx, vy),
                        "actual": (w_region, w_level, b["x"], b["y"], b["vx"], b["vy"]),
                    }
                )

    _, _, ref_mass, ref_px, ref_py, ref_e0 = reference.totals()
    _, _, _, end_px, end_py, end_e = world.totals()
    ref_scale = max(abs(ref_px), abs(ref_py), 1e-30)
    return {
        "ticks_verified": last_tick,
        "records_compared": compared,
        "mismatch_count": len(mismatches),
        "mismatches": mismatches[:20],
        "max_position_deviation": max_pos_dev,
        "momentum_drift": max(abs(end_px - ref_px), abs(end_py - ref_py)) / ref_scale,
        "energy_drift": abs(end_e - ref_e0) / abs(ref_e0),
        "final_world_hash": world.world_hash(),
    }


def check_reference_match_gravity(summary: dict, *, threshold: float = 0.0) -> DiagnosticResult:
    count = summary["mismatch_count"]
    return DiagnosticResult(
        name="ontos_reference_match",
        passed=count <= threshold,
        threshold=float(threshold),
        value=float(count),
        detail={
            "ticks_verified": summary["ticks_verified"],
            "records_compared": summary["records_compared"],
            "first_mismatches": summary["mismatches"],
        },
    )


def check_bounded_drift(summary: dict, *, pos_tol: float = 5e-2, mom_tol: float = 5e-2, energy_tol: float = 1e-3) -> DiagnosticResult:
    pos = summary["max_position_deviation"]
    mom = summary["momentum_drift"]
    energy = summary["energy_drift"]
    return DiagnosticResult(
        name="ontos_window_drift",
        passed=pos <= pos_tol and mom <= mom_tol and energy <= energy_tol,
        threshold=float(pos_tol),
        value=float(max(pos, mom, energy)),
        detail={
            "max_position_deviation": pos,
            "momentum_drift_relative": mom,
            "energy_drift_relative": energy,
            "tolerances": {"position": pos_tol, "momentum": mom_tol, "energy": energy_tol},
        },
    )


def _main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m simval.ontos",
        description="Verify an ontos record stream (life or gravity) against this independent reference",
    )
    parser.add_argument("stream", help="path to a .stream file")
    parser.add_argument("seed", type=int, help="world seed the stream was produced with")
    args = parser.parse_args(argv)
    try:
        data = Path(args.stream).read_bytes()
        if len(data) >= 8 and data[4:8] == struct.pack("<I", 2):
            summary = verify_stream_gravity(args.stream, args.seed)
            ok = summary["mismatch_count"] == 0
            print(
                f"ontos gravity stream: {'OK' if ok else 'MISMATCH'} | ticks={summary['ticks_verified']} "
                f"records={summary['records_compared']} mismatches={summary['mismatch_count']} "
                f"max_pos_dev={summary['max_position_deviation']:.3e} "
                f"mom_drift={summary['momentum_drift']:.3e} energy_drift={summary['energy_drift']:.3e} "
                f"final_world_hash={summary['final_world_hash']:016x}"
            )
            for m in summary["mismatches"]:
                print(f"  MISMATCH: {m}")
            return 0 if ok else 1
        from simval.ontos import verify_stream

        summary = verify_stream(args.stream, args.seed)
        ok = summary["mismatch_count"] == 0 and summary["tick_monotonic"]
        print(
            f"ontos stream: {'OK' if ok else 'MISMATCH'} | ticks={summary['ticks_verified']} "
            f"records={summary['records_compared']} mismatches={summary['mismatch_count']} "
            f"final_population={summary['final_population']} "
            f"final_world_hash={summary['final_world_hash']:016x}"
        )
        for m in summary["mismatches"]:
            print(f"  MISMATCH: {m}")
        return 0 if ok else 1
    except (FileNotFoundError, ValueError) as e:
        print(f"simval.ontos: error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_main())
